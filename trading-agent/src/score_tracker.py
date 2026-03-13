"""
Score tracker — tracks win/loss rate per symbol for Claude feedback loop.

Maintains in-memory scores loaded from PostgreSQL ClaudeDecision table.
Scores are recalculated on position close and fed back to Claude's next prompt.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import sqrt

import structlog

logger = structlog.get_logger()


@dataclass
class SymbolScore:
    symbol: str
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    win_rate: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    total_pnl: float = 0.0
    sharpe_ratio: float = 0.0
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ScoreTracker:
    def __init__(self):
        # {user_id: {symbol: SymbolScore}}
        self._scores: dict[str, dict[str, SymbolScore]] = {}

    async def load_scores(self, pool, user_id: str) -> dict[str, SymbolScore]:
        """Load aggregated scores from ClaudeDecision table."""
        try:
            rows = await pool.fetch(
                """
                SELECT
                    symbol,
                    COUNT(*) FILTER (WHERE outcome IS NOT NULL) as total,
                    COUNT(*) FILTER (WHERE outcome = 'WIN') as wins,
                    COUNT(*) FILTER (WHERE outcome = 'LOSS') as losses,
                    COALESCE(AVG("actualPnl") FILTER (WHERE outcome = 'WIN'), 0) as avg_win,
                    COALESCE(AVG("actualPnl") FILTER (WHERE outcome = 'LOSS'), 0) as avg_loss,
                    COALESCE(SUM("actualPnl") FILTER (WHERE outcome IS NOT NULL), 0) as total_pnl
                FROM "ClaudeDecision"
                WHERE "userId" = $1 AND action = 'OPEN_LONG'
                GROUP BY symbol
                """,
                user_id,
            )

            scores = {}
            for r in rows:
                total = r["total"] or 0
                wins = r["wins"] or 0
                losses = r["losses"] or 0
                win_rate = wins / total if total > 0 else 0.0
                avg_win = float(r["avg_win"] or 0)
                avg_loss = float(r["avg_loss"] or 0)
                total_pnl = float(r["total_pnl"] or 0)

                # Calculate Sharpe from individual trade returns
                sharpe = await self._calculate_sharpe(pool, user_id, r["symbol"])

                scores[r["symbol"]] = SymbolScore(
                    symbol=r["symbol"],
                    total_trades=total,
                    wins=wins,
                    losses=losses,
                    win_rate=win_rate,
                    avg_win_pct=avg_win,
                    avg_loss_pct=avg_loss,
                    total_pnl=total_pnl,
                    sharpe_ratio=sharpe,
                )

            self._scores[user_id] = scores
            logger.info(
                "Scores loaded",
                user_id=user_id,
                symbols=len(scores),
            )
            return scores
        except Exception as e:
            logger.warning("Failed to load scores", user_id=user_id, error=str(e))
            return {}

    async def _calculate_sharpe(
        self, pool, user_id: str, symbol: str
    ) -> float:
        """Calculate Sharpe ratio from trade-level P&L returns."""
        try:
            rows = await pool.fetch(
                """
                SELECT "actualPnl", "entryPrice"
                FROM "ClaudeDecision"
                WHERE "userId" = $1 AND symbol = $2
                  AND outcome IS NOT NULL AND "entryPrice" > 0
                ORDER BY "createdAt" DESC
                LIMIT 50
                """,
                user_id, symbol,
            )
            if len(rows) < 3:
                return 0.0

            returns = []
            for r in rows:
                entry = float(r["entryPrice"])
                pnl = float(r["actualPnl"] or 0)
                if entry > 0:
                    returns.append(pnl / entry)

            if len(returns) < 3:
                return 0.0

            mean_ret = sum(returns) / len(returns)
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            std_ret = sqrt(variance) if variance > 0 else 0.0001

            return round(mean_ret / std_ret, 3) if std_ret > 0 else 0.0
        except Exception:
            return 0.0

    def get_symbol_score(self, user_id: str, symbol: str) -> SymbolScore | None:
        """Get cached score for a symbol. Returns None if no history."""
        return self._scores.get(user_id, {}).get(symbol)

    def get_all_scores(self, user_id: str) -> dict[str, SymbolScore]:
        return self._scores.get(user_id, {})

    async def record_open(
        self, pool, user_id: str, symbol: str,
        decision_id: str, entry_price: float,
        claude_confidence: float, claude_reasoning: str,
        expected_pnl: float,
    ) -> None:
        """Called after a position is opened. Updates pending decision record."""
        try:
            await pool.execute(
                """
                UPDATE "ClaudeDecision"
                SET "entryPrice" = $1, "executionStatus" = 'EXECUTED'
                WHERE id = $2
                """,
                entry_price, decision_id,
            )
        except Exception as e:
            logger.warning("Failed to record open in score", error=str(e))

    async def record_close(
        self, pool, user_id: str, symbol: str,
        exit_price: float, actual_pnl: float,
    ) -> None:
        """Called when a position closes. Updates the most recent open decision."""
        try:
            outcome = "WIN" if actual_pnl > 0 else "LOSS"
            now = datetime.now(timezone.utc)

            # Update the most recent EXECUTED decision for this symbol
            await pool.execute(
                """
                UPDATE "ClaudeDecision"
                SET "exitPrice" = $1, "actualPnl" = $2, outcome = $3,
                    "closedAt" = $4
                WHERE id = (
                    SELECT id FROM "ClaudeDecision"
                    WHERE "userId" = $5 AND symbol = $6
                      AND action = 'OPEN_LONG'
                      AND "executionStatus" = 'EXECUTED'
                      AND outcome IS NULL
                    ORDER BY "createdAt" DESC
                    LIMIT 1
                )
                """,
                exit_price, actual_pnl, outcome, now,
                user_id, symbol,
            )

            # Recalculate scores for this symbol
            await self._recalculate_symbol(pool, user_id, symbol)

            logger.info(
                "Trade scored",
                user_id=user_id, symbol=symbol,
                pnl=round(actual_pnl, 2), outcome=outcome,
            )
        except Exception as e:
            logger.warning("Failed to record close in score", error=str(e))

    async def _recalculate_symbol(
        self, pool, user_id: str, symbol: str
    ) -> None:
        """Recalculate score for a single symbol after trade closes."""
        row = await pool.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE outcome IS NOT NULL) as total,
                COUNT(*) FILTER (WHERE outcome = 'WIN') as wins,
                COUNT(*) FILTER (WHERE outcome = 'LOSS') as losses,
                COALESCE(AVG("actualPnl") FILTER (WHERE outcome = 'WIN'), 0) as avg_win,
                COALESCE(AVG("actualPnl") FILTER (WHERE outcome = 'LOSS'), 0) as avg_loss,
                COALESCE(SUM("actualPnl") FILTER (WHERE outcome IS NOT NULL), 0) as total_pnl
            FROM "ClaudeDecision"
            WHERE "userId" = $1 AND symbol = $2 AND action = 'OPEN_LONG'
            """,
            user_id, symbol,
        )

        if not row:
            return

        total = row["total"] or 0
        wins = row["wins"] or 0
        losses = row["losses"] or 0
        sharpe = await self._calculate_sharpe(pool, user_id, symbol)

        score = SymbolScore(
            symbol=symbol,
            total_trades=total,
            wins=wins,
            losses=losses,
            win_rate=wins / total if total > 0 else 0.0,
            avg_win_pct=float(row["avg_win"] or 0),
            avg_loss_pct=float(row["avg_loss"] or 0),
            total_pnl=float(row["total_pnl"] or 0),
            sharpe_ratio=sharpe,
        )

        if user_id not in self._scores:
            self._scores[user_id] = {}
        self._scores[user_id][symbol] = score
