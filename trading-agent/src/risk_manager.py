"""
Risk management — position limits, daily loss, drawdown, position sizing.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone

import structlog

from .db import AgentConfig, PositionRisk
from .brokers.base import AccountInfo, Position
from .position_tracker import PositionTracker

logger = structlog.get_logger()


@dataclass
class DailyRiskState:
    date: date = field(default_factory=lambda: datetime.now(timezone.utc).date())
    daily_realized_pnl: float = 0.0
    peak_equity: float = 0.0
    current_equity: float = 0.0
    decisions_today: int = 0
    trades_executed_today: int = 0


class RiskManager:
    def __init__(self):
        self._state: dict[str, DailyRiskState] = {}

    def _get_state(self, user_id: str) -> DailyRiskState:
        today = datetime.now(timezone.utc).date()
        state = self._state.get(user_id)
        if not state or state.date != today:
            # Reset daily state at midnight UTC
            state = DailyRiskState(date=today)
            self._state[user_id] = state
        return state

    def can_open_position(
        self,
        config: AgentConfig,
        tracker: PositionTracker,
        user_id: str,
        symbol: str,
    ) -> tuple[bool, str]:
        """Check if we're allowed to open a new position."""
        # Max concurrent positions
        if tracker.get_open_count(user_id) >= config.max_concurrent_positions:
            return False, f"Max positions reached ({config.max_concurrent_positions})"

        # Allowed symbols filter
        if config.allowed_symbols and symbol not in config.allowed_symbols:
            return False, f"Symbol {symbol} not in allowed list"

        # Already have an agent-opened position in this symbol
        # Ignore pre-existing positions (avg_entry_price == 0 means not opened by agent)
        pos = tracker.get_position(user_id, symbol)
        if pos and pos.avg_entry_price > 0:
            return False, f"Already have position in {symbol}"

        # Daily loss limit
        state = self._get_state(user_id)
        if state.daily_realized_pnl <= -config.daily_loss_limit_usd:
            return False, f"Daily loss limit reached (${state.daily_realized_pnl:.2f})"

        # Max drawdown
        if state.peak_equity > 0:
            drawdown_pct = (
                (state.peak_equity - state.current_equity)
                / state.peak_equity * 100
            )
            if drawdown_pct >= config.max_drawdown_pct:
                return False, f"Max drawdown reached ({drawdown_pct:.1f}%)"

        return True, "OK"

    def calculate_position_size(
        self,
        config: AgentConfig,
        signal: dict,
        account: AccountInfo,
        kelly_fraction: float | None = None,
    ) -> float:
        """Calculate position size in base currency units.

        If kelly_fraction is provided (from PortfolioOptimizer), it replaces
        the flat aggressiveness multiplier. Backward compatible — pass None
        to use the original aggressiveness logic.
        """
        # Base size in USD
        base_usd = config.max_position_size_usd

        # Sizing multiplier: Kelly-derived or flat aggressiveness fallback
        if kelly_fraction is not None:
            size_mult = kelly_fraction
        else:
            size_mult = 0.5 + config.aggressiveness * 0.5  # original logic
        adjusted_usd = base_usd * size_mult

        # Adjust by confidence (narrower band = more confident = bigger)
        conf_low = signal.get("confidence_low", 0)
        conf_high = signal.get("confidence_high", 0)
        price = signal.get("current_price", 1)
        if price > 0 and conf_high > conf_low:
            band_pct = (conf_high - conf_low) / price
            # Narrower band (< 2%) = higher confidence = up to 1.2x
            # Wider band (> 5%) = lower confidence = down to 0.6x
            confidence_mult = max(0.6, min(1.2, 1.0 - (band_pct - 0.02) * 10))
            adjusted_usd *= confidence_mult

        # Never use more than 90% of buying power (leave some for fees)
        max_bp = account.buying_power * 0.90
        final_usd = min(adjusted_usd, max_bp)

        # Ensure minimum order value ($5 for Bitget spot minimum)
        # If buying power is too low, return 0 to skip the trade
        if final_usd < 5.0:
            if account.buying_power >= 5.5:
                final_usd = 5.0  # Force minimum
            else:
                logger.warning(
                    "Insufficient buying power for minimum order",
                    buying_power=round(account.buying_power, 2),
                    min_required=5.0,
                )
                return 0.0

        # Convert USD to quantity, rounded to 6 decimal places (Bitget precision)
        if price <= 0:
            return 0.0
        qty = final_usd / price
        logger.info(
            "Position size calculated",
            base_usd=base_usd, size_mult=round(size_mult, 3),
            kelly=kelly_fraction is not None,
            adjusted_usd=round(adjusted_usd, 2), max_bp=round(max_bp, 2),
            final_usd=round(final_usd, 2), qty=round(qty, 6), price=price,
        )
        return round(qty, 6)

    def should_close_position(
        self,
        position: Position,
        signal: dict,
        risk: PositionRisk | None,
    ) -> tuple[bool, str]:
        """Check if an existing position should be closed."""
        price = position.current_price

        # Stop loss
        if risk and risk.stop_loss_price and price <= risk.stop_loss_price:
            return True, f"Stop loss hit (${risk.stop_loss_price})"

        # Take profit
        if risk and risk.take_profit_price and price >= risk.take_profit_price:
            return True, f"Take profit hit (${risk.take_profit_price})"

        # Signal reversal: long position + SELL signal
        sig = signal.get("signal", "HOLD")
        if position.side == "long" and sig == "SELL":
            return True, "SELL signal on long position"

        return False, ""

    def record_trade_pnl(self, user_id: str, pnl: float) -> None:
        state = self._get_state(user_id)
        state.daily_realized_pnl += pnl
        state.trades_executed_today += 1

    def record_decision(self, user_id: str) -> None:
        state = self._get_state(user_id)
        state.decisions_today += 1

    def update_equity(self, user_id: str, equity: float) -> None:
        state = self._get_state(user_id)
        state.current_equity = equity
        if equity > state.peak_equity:
            state.peak_equity = equity

    def get_state(self, user_id: str) -> DailyRiskState:
        return self._get_state(user_id)
