"""
Risk Guardian — independent portfolio-level veto layer.

Runs BEFORE the DecisionEngine so it can block signals that would violate
portfolio-wide constraints, regardless of Claude's opinion.

Checks (in order):
  1. Daily decision cap — hard stop if too many decisions today
  2. DANGER alert — hard veto on BUY when Market Sentinel reports anomaly
  3. Volatile regime position cap — max 2 open positions in VOLATILE regime
  4. Portfolio concentration — reject if single position would exceed 40%
"""

from dataclasses import dataclass

import structlog

from .db import AgentConfig
from .position_tracker import PositionTracker
from .risk_manager import RiskManager

logger = structlog.get_logger()


@dataclass
class VetoResult:
    vetoed: bool
    reason: str
    severity: str = "NONE"    # "NONE" | "SOFT" | "HARD"


class RiskGuardian:
    MAX_CONCENTRATION_PCT = 0.40   # 40% of portfolio value in one symbol
    VOLATILE_MAX_POSITIONS = 2     # Cap positions in VOLATILE regime
    MAX_DECISIONS_PER_DAY  = 50    # Hard daily decision ceiling

    def evaluate(
        self,
        signal: dict,
        config: AgentConfig,
        risk_mgr: RiskManager,
        tracker: PositionTracker,
        user_id: str,
    ) -> VetoResult:
        action_hint = signal.get("signal", "HOLD")
        symbol      = signal.get("symbol", "")
        alert_level = signal.get("alert_level", "NORMAL")
        regime      = signal.get("regime", "")

        # Guardian only applies veto logic to BUY signals
        if action_hint != "BUY":
            return VetoResult(vetoed=False, reason="Non-BUY — no veto needed.")

        state = risk_mgr.get_state(user_id)

        # ── 1. Daily decision cap ────────────────────────────────────────────
        if state.decisions_today >= self.MAX_DECISIONS_PER_DAY:
            return VetoResult(
                vetoed=True,
                reason=(
                    f"Daily decision cap reached "
                    f"({state.decisions_today}/{self.MAX_DECISIONS_PER_DAY})"
                ),
                severity="HARD",
            )

        # ── 2. DANGER alert (Market Sentinel anomaly) ────────────────────────
        if alert_level == "DANGER":
            return VetoResult(
                vetoed=True,
                reason=(
                    "Market Sentinel DANGER alert — BUY blocked until "
                    "anomaly resolves."
                ),
                severity="HARD",
            )

        # ── 3. Volatile regime position cap ─────────────────────────────────
        is_volatile = "VOLATILE" in regime
        open_count  = tracker.get_open_count(user_id)
        if is_volatile and open_count >= self.VOLATILE_MAX_POSITIONS:
            return VetoResult(
                vetoed=True,
                reason=(
                    f"Volatile regime: max {self.VOLATILE_MAX_POSITIONS} positions "
                    f"(currently {open_count} open)"
                ),
                severity="SOFT",
            )

        # ── 4. Portfolio concentration ───────────────────────────────────────
        portfolio_value = tracker.get_total_value(user_id)
        if portfolio_value > 0:
            price        = signal.get("current_price", 1.0) or 1.0
            aggr_mult    = 0.5 + config.aggressiveness * 0.5
            proposed_usd = config.max_position_size_usd * aggr_mult
            position_pct = proposed_usd / (portfolio_value + proposed_usd)
            if position_pct > self.MAX_CONCENTRATION_PCT:
                return VetoResult(
                    vetoed=True,
                    reason=(
                        f"Concentration limit: proposed position would be "
                        f"{position_pct * 100:.1f}% of portfolio "
                        f"(max {self.MAX_CONCENTRATION_PCT * 100:.0f}%)"
                    ),
                    severity="SOFT",
                )

        return VetoResult(vetoed=False, reason="All guardian checks passed.", severity="NONE")
