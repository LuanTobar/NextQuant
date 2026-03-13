"""
Execution Specialist — handles order placement, recording, and position lifecycle.

Extracted from agent_loop._process_signal_for_user to give execution
a clear single-responsibility: take a final decision and execute it.
"""

from dataclasses import dataclass

import structlog

from .brokers.base import BrokerClient, OrderRequest
from .db import save_order
from .position_tracker import PositionTracker
from .risk_manager import RiskManager
from .score_tracker import ScoreTracker

logger = structlog.get_logger()


@dataclass
class ExecutionResult:
    action: str
    symbol: str
    status: str                    # "EXECUTED" | "SKIPPED" | "FAILED"
    broker_order_id: str | None = None
    pnl: float = 0.0


class ExecutionSpecialist:
    """
    Executes a finalized trade decision:
      - Places order via broker client
      - Records order in PostgreSQL
      - Updates PositionTracker and RiskManager
      - Notifies ScoreTracker
    """

    async def open_long(
        self,
        user_id: str,
        symbol: str,
        quantity: float,
        signal_data: dict,
        claude_rec,
        client: BrokerClient,
        pool,
        conn_id: str | None,
        tracker: PositionTracker,
        scorer: ScoreTracker,
        claude_decision_id: str | None,
    ) -> ExecutionResult:
        try:
            order_resp = await client.place_order(OrderRequest(
                symbol=symbol, side="buy",
                quantity=quantity,
                type="market", time_in_force="gtc",
            ))
            broker_order_id = order_resp.broker_id

            if pool and conn_id:
                await save_order(
                    pool, user_id, conn_id,
                    symbol, "BUY", quantity, "market",
                    broker_order_id,
                    {
                        "source": "agent",
                        "signal": signal_data.get("signal"),
                        "claude_recommendation": claude_rec.recommendation,
                        "claude_confidence": round(claude_rec.confidence, 3),
                    },
                )

            entry_price = signal_data.get("current_price", 0)
            tracker.record_open(user_id, symbol, quantity, entry_price)

            if pool and claude_decision_id:
                await scorer.record_open(
                    pool, user_id, symbol,
                    decision_id=claude_decision_id,
                    entry_price=entry_price,
                    claude_confidence=claude_rec.confidence,
                    claude_reasoning=claude_rec.reasoning,
                    expected_pnl=claude_rec.expected_pnl,
                )

            logger.info(
                "Position opened",
                user_id=user_id, symbol=symbol,
                qty=quantity, price=entry_price,
                broker_order_id=broker_order_id,
            )
            return ExecutionResult(
                action="OPEN_LONG", symbol=symbol,
                status="EXECUTED", broker_order_id=broker_order_id,
            )

        except Exception as e:
            logger.error(
                "Failed to open position",
                user_id=user_id, symbol=symbol, error=str(e),
            )
            return ExecutionResult(action="OPEN_LONG", symbol=symbol, status="FAILED")

    async def close_long(
        self,
        user_id: str,
        symbol: str,
        quantity: float,
        signal_data: dict,
        claude_rec,
        client: BrokerClient,
        pool,
        conn_id: str | None,
        tracker: PositionTracker,
        risk_mgr: RiskManager,
        scorer: ScoreTracker,
    ) -> ExecutionResult:
        try:
            order_resp = await client.close_position(symbol, quantity)
            broker_order_id = order_resp.broker_id

            if pool and conn_id:
                await save_order(
                    pool, user_id, conn_id,
                    symbol, "SELL", quantity, "market",
                    broker_order_id,
                    {
                        "source": "agent",
                        "signal": signal_data.get("signal"),
                        "claude_recommendation": claude_rec.recommendation,
                    },
                )

            position = tracker.get_position(user_id, symbol)
            pnl = 0.0
            if position:
                pnl = (
                    signal_data.get("current_price", 0) - position.avg_entry_price
                ) * quantity
                risk_mgr.record_trade_pnl(user_id, pnl)

                if pool:
                    await scorer.record_close(
                        pool, user_id, symbol,
                        signal_data.get("current_price", 0), pnl,
                    )

            tracker.record_close(user_id, symbol)

            logger.info(
                "Position closed",
                user_id=user_id, symbol=symbol,
                qty=quantity, pnl=round(pnl, 2),
                broker_order_id=broker_order_id,
            )
            return ExecutionResult(
                action="CLOSE", symbol=symbol,
                status="EXECUTED", broker_order_id=broker_order_id,
                pnl=pnl,
            )

        except Exception as e:
            logger.error(
                "Failed to close position",
                user_id=user_id, symbol=symbol, error=str(e),
            )
            return ExecutionResult(action="CLOSE", symbol=symbol, status="FAILED")
