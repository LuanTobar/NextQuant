"""
Decision engine — evaluates ML signals against risk rules to produce trade decisions.
"""

from dataclasses import dataclass

from .db import AgentConfig, PositionRisk
from .risk_manager import RiskManager
from .position_tracker import PositionTracker
from .brokers.base import AccountInfo


@dataclass
class Decision:
    action: str         # "OPEN_LONG" | "CLOSE" | "HOLD"
    symbol: str
    quantity: float = 0.0
    reason: str = ""
    confidence: float = 0.0


class DecisionEngine:
    def evaluate(
        self,
        signal: dict,
        config: AgentConfig,
        risk_mgr: RiskManager,
        tracker: PositionTracker,
        user_id: str,
        account: AccountInfo,
        position_risks: list[PositionRisk],
        kelly_fraction: float | None = None,
    ) -> Decision:
        symbol = signal.get("symbol", "")
        sig = signal.get("signal", "HOLD")
        price = signal.get("current_price", 0)

        # Record this evaluation
        risk_mgr.record_decision(user_id)

        # Check if we have an agent-opened position
        # Ignore pre-existing positions (not tracked by agent) and dust < $1
        position = tracker.get_position(user_id, symbol)
        if position and (position.market_value < 1.0 or position.avg_entry_price == 0):
            position = None  # Pre-existing or dust — treat as no position

        if position:
            # Find risk rules for this position
            risk = next(
                (r for r in position_risks if r.symbol == symbol),
                None,
            )
            should_close, reason = risk_mgr.should_close_position(
                position, signal, risk
            )
            if should_close:
                return Decision(
                    action="CLOSE", symbol=symbol,
                    quantity=position.quantity,
                    reason=reason,
                )

        # No position — evaluate opening
        if sig == "BUY" and not position:
            can_open, reason = risk_mgr.can_open_position(
                config, tracker, user_id, symbol,
            )
            if not can_open:
                return Decision(
                    action="HOLD", symbol=symbol,
                    reason=f"BUY signal blocked: {reason}",
                )

            qty = risk_mgr.calculate_position_size(config, signal, account,
                                                   kelly_fraction=kelly_fraction)
            if qty <= 0:
                return Decision(
                    action="HOLD", symbol=symbol,
                    reason="Calculated position size is zero",
                )

            conf_low = signal.get("confidence_low", 0)
            conf_high = signal.get("confidence_high", 0)
            regime = signal.get("regime", "?")
            return Decision(
                action="OPEN_LONG", symbol=symbol,
                quantity=qty,
                reason=f"BUY signal, regime {regime}, range ${conf_low:.2f}-${conf_high:.2f}",
                confidence=(conf_high - conf_low) / price if price > 0 else 0,
            )

        # SELL signal without position = no action (spot only, no shorting)
        if sig == "SELL" and not position:
            return Decision(
                action="HOLD", symbol=symbol,
                reason="SELL signal but no position (spot-only, no shorting)",
            )

        return Decision(
            action="HOLD", symbol=symbol,
            reason=f"Signal is {sig}, no action",
        )
