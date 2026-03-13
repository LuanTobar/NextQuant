"""
Strategy Architect — orchestrates the full per-signal decision pipeline.

Pipeline (in order):
  1. Risk Guardian pre-check  — portfolio-level veto before anything else
  2. Load position risks
  2.5 Portfolio Optimizer     — Half-Kelly + regime + concentration → kelly_fraction
  3. Decision Engine          — deterministic rule-based decision
  4. Claude evaluation        — LLM validation with full context
  5. Persist Claude decision
  6. Recommendation apply     — honour REJECT / REDUCE from Claude

Returns an ArchitectResult that agent_loop hands to ExecutionSpecialist.
"""

from dataclasses import dataclass

import structlog

from .claude_layer import ClaudeLayer, ClaudeRecommendation
from .db import AgentConfig, load_position_risks, load_recent_signal_history, save_claude_decision
from .decision_engine import Decision, DecisionEngine
from .portfolio_optimizer import PortfolioOptimizer
from .risk_guardian import RiskGuardian, VetoResult
from .risk_manager import RiskManager
from .position_tracker import PositionTracker
from .brokers.base import AccountInfo
from .score_tracker import ScoreTracker

logger = structlog.get_logger()


@dataclass
class ArchitectResult:
    decision: Decision
    claude_rec: ClaudeRecommendation
    guardian_result: VetoResult
    claude_decision_id: str | None


class StrategyArchitect:
    """
    Owns the signal → decision → validation pipeline for a single user/signal pair.

    agent_loop creates ONE StrategyArchitect instance and reuses it across all
    signals/users.  All per-call state is passed as arguments (no shared mutable
    state between calls).
    """

    def __init__(
        self,
        engine: DecisionEngine,
        claude: ClaudeLayer,
        guardian: RiskGuardian,
        risk_mgr: RiskManager,
        tracker: PositionTracker,
        scorer: ScoreTracker,
        optimizer: PortfolioOptimizer,
    ):
        self._engine    = engine
        self._claude    = claude
        self._guardian  = guardian
        self._risk_mgr  = risk_mgr
        self._tracker   = tracker
        self._scorer    = scorer
        self._optimizer = optimizer

    async def evaluate(
        self,
        user_id: str,
        config: AgentConfig,
        signal_data: dict,
        account: AccountInfo,
        pool,
        http_client,
        questdb_url: str,
        risk_profile: dict | None,
    ) -> ArchitectResult:
        symbol = signal_data.get("symbol", "")

        # ── 1. Risk Guardian pre-check ───────────────────────────────────────
        guardian_result = self._guardian.evaluate(
            signal_data, config, self._risk_mgr, self._tracker, user_id
        )
        if guardian_result.vetoed:
            logger.info(
                "Guardian vetoed",
                user_id=user_id, symbol=symbol,
                severity=guardian_result.severity,
                reason=guardian_result.reason,
            )
            hold = Decision(
                action="HOLD", symbol=symbol,
                reason=f"Guardian [{guardian_result.severity}]: {guardian_result.reason}",
            )
            return ArchitectResult(
                decision=hold,
                claude_rec=ClaudeRecommendation(
                    execute=False, confidence=1.0,
                    reasoning=guardian_result.reason,
                    recommendation="REJECT",
                ),
                guardian_result=guardian_result,
                claude_decision_id=None,
            )

        # ── 2. Load position risks ───────────────────────────────────────────
        position_risks = []
        if pool:
            position_risks = await load_position_risks(pool, user_id, config.broker)

        # ── 2.5. Portfolio Optimizer ─────────────────────────────────────────
        symbol_score   = self._scorer.get_symbol_score(user_id, symbol)
        open_positions = self._tracker.get_all_positions(user_id)
        kelly_fraction, kelly_meta = self._optimizer.optimize(
            symbol=symbol,
            regime=signal_data.get("regime", "SIDEWAYS"),
            score=symbol_score,
            open_positions=open_positions,
        )
        signal_data = {**signal_data,
            "kelly_fraction": kelly_meta["final_fraction"],
            "kelly_base":     kelly_meta["kelly_base"],
            "regime_mult":    kelly_meta["regime_mult"],
            "conc_penalty":   kelly_meta["conc_penalty"],
        }
        logger.info("Kelly sizing", user_id=user_id, symbol=symbol, **kelly_meta)

        # ── 3. Decision Engine ───────────────────────────────────────────────
        decision = self._engine.evaluate(
            signal_data, config, self._risk_mgr, self._tracker,
            user_id, account, position_risks,
            kelly_fraction=kelly_fraction,
        )
        logger.info(
            "Engine decision",
            user_id=user_id, symbol=symbol,
            action=decision.action, reason=decision.reason,
        )

        # ── 4. Claude evaluation ─────────────────────────────────────────────
        signal_history = await load_recent_signal_history(
            http_client, questdb_url, symbol, limit=20
        )

        claude_rec = await self._claude.evaluate(
            signal_data=signal_data,
            decision=decision,
            config=config,
            risk_state=self._risk_mgr.get_state(user_id),
            positions=self._tracker.get_all_positions(user_id),
            account=account,
            symbol_score=symbol_score,
            position_risks=position_risks,
            signal_history=signal_history,
            risk_profile=risk_profile,
        )

        # ── 5. Persist Claude decision ───────────────────────────────────────
        claude_decision_id = None
        if pool:
            try:
                claude_decision_id = await save_claude_decision(
                    pool, user_id, symbol,
                    decision.action, signal_data, claude_rec,
                )
                claude_rec.decision_id = claude_decision_id
            except Exception as e:
                logger.warning("Failed to save Claude decision", error=str(e))

        # ── 6. Apply Claude recommendation ───────────────────────────────────
        if decision.action in ("OPEN_LONG", "CLOSE") and not claude_rec.execute:
            logger.info(
                "Claude REJECTED",
                user_id=user_id, symbol=symbol,
                reason=claude_rec.reasoning,
            )
            decision = Decision(
                action="HOLD", symbol=symbol,
                reason=f"Claude rejected: {claude_rec.reasoning}",
            )
            if pool and claude_decision_id:
                try:
                    await pool.execute(
                        'UPDATE "ClaudeDecision" SET "executionStatus" = $1 WHERE id = $2',
                        "SKIPPED", claude_decision_id,
                    )
                except Exception:
                    pass

        elif claude_rec.recommendation == "REDUCE" and decision.action == "OPEN_LONG":
            original_qty   = decision.quantity
            decision.quantity = round(decision.quantity * claude_rec.adjusted_size, 6)
            logger.info(
                "Claude REDUCED size",
                user_id=user_id, symbol=symbol,
                original_qty=original_qty,
                adjusted_qty=decision.quantity,
                multiplier=claude_rec.adjusted_size,
            )

        return ArchitectResult(
            decision=decision,
            claude_rec=claude_rec,
            guardian_result=guardian_result,
            claude_decision_id=claude_decision_id,
        )
