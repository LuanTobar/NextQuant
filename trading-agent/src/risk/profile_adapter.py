"""
Profile Adapter — Sprint 1.5.

Maps a RiskScoreResult to concrete AgentConfig parameter overrides.
These parameters directly control how the trading agent sizes positions
and manages risk on behalf of the user.

Parameter derivation table:

  Category       | maxPositionUsd | maxConcurrent | dailyLossUsd | maxDD% | aggressiveness
  ---------------|----------------|---------------|--------------|--------|---------------
  CONSERVATIVE   |      50        |       2       |     100      |   5    |    0.15
  MODERATE       |     150        |       3       |     400      |  12    |    0.45
  AGGRESSIVE     |     500        |       5       |    1 000     |  22    |    0.75
  SPECULATIVE    |   1 000        |       8       |    3 000     |  40    |    0.92
"""

from __future__ import annotations

from dataclasses import dataclass, asdict

from .profiler import RiskScoreResult


# ── Config table ───────────────────────────────────────────────────────────────

_CONFIG_TABLE: dict[str, dict] = {
    "CONSERVATIVE": {
        "max_position_size_usd":    50.0,
        "max_concurrent_positions": 2,
        "daily_loss_limit_usd":     100.0,
        "max_drawdown_pct":         5.0,
        "aggressiveness":           0.15,
    },
    "MODERATE": {
        "max_position_size_usd":    150.0,
        "max_concurrent_positions": 3,
        "daily_loss_limit_usd":     400.0,
        "max_drawdown_pct":         12.0,
        "aggressiveness":           0.45,
    },
    "AGGRESSIVE": {
        "max_position_size_usd":    500.0,
        "max_concurrent_positions": 5,
        "daily_loss_limit_usd":     1_000.0,
        "max_drawdown_pct":         22.0,
        "aggressiveness":           0.75,
    },
    "SPECULATIVE": {
        "max_position_size_usd":    1_000.0,
        "max_concurrent_positions": 8,
        "daily_loss_limit_usd":     3_000.0,
        "max_drawdown_pct":         40.0,
        "aggressiveness":           0.92,
    },
}

# Category order for boundary interpolation
_ORDERED_CATEGORIES = ["CONSERVATIVE", "MODERATE", "AGGRESSIVE", "SPECULATIVE"]
_CATEGORY_MIDPOINTS = {
    "CONSERVATIVE": 0.125,
    "MODERATE":     0.375,
    "AGGRESSIVE":   0.625,
    "SPECULATIVE":  0.875,
}


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class AgentConfigOverride:
    """AgentConfig parameters derived from a user's risk profile."""
    max_position_size_usd:    float
    max_concurrent_positions: int
    daily_loss_limit_usd:     float
    max_drawdown_pct:         float
    aggressiveness:           float
    risk_category:            str
    risk_score:               float

    def to_dict(self) -> dict:
        """Plain dict for JSON serialisation or DB storage."""
        return {
            "maxPositionSizeUsd":    self.max_position_size_usd,
            "maxConcurrentPositions": self.max_concurrent_positions,
            "dailyLossLimitUsd":     self.daily_loss_limit_usd,
            "maxDrawdownPct":        self.max_drawdown_pct,
            "aggressiveness":        self.aggressiveness,
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def derive_agent_config(result: RiskScoreResult) -> AgentConfigOverride:
    """
    Derive AgentConfig parameters from a RiskScoreResult.

    Uses the scored category as the primary lookup.  Within a category the
    values are fixed (not linearly interpolated) to keep behaviour predictable
    and auditable — users know exactly what config they get for each category.

    Args:
        result: Output of profiler.score_profile()

    Returns:
        AgentConfigOverride populated with all config parameters.
    """
    cat  = result.risk_category.upper()
    base = _CONFIG_TABLE.get(cat, _CONFIG_TABLE["MODERATE"])

    return AgentConfigOverride(
        max_position_size_usd    = float(base["max_position_size_usd"]),
        max_concurrent_positions = int(base["max_concurrent_positions"]),
        daily_loss_limit_usd     = float(base["daily_loss_limit_usd"]),
        max_drawdown_pct         = float(base["max_drawdown_pct"]),
        aggressiveness           = float(base["aggressiveness"]),
        risk_category            = cat,
        risk_score               = result.risk_score,
    )


def config_for_category(category: str) -> AgentConfigOverride:
    """
    Return the AgentConfigOverride for a given category string directly,
    without needing a full RiskScoreResult.

    Useful for seeding defaults in tests and migrations.
    """
    cat = category.upper()
    score = _CATEGORY_MIDPOINTS.get(cat, 0.375)
    base  = _CONFIG_TABLE.get(cat, _CONFIG_TABLE["MODERATE"])

    return AgentConfigOverride(
        max_position_size_usd    = float(base["max_position_size_usd"]),
        max_concurrent_positions = int(base["max_concurrent_positions"]),
        daily_loss_limit_usd     = float(base["daily_loss_limit_usd"]),
        max_drawdown_pct         = float(base["max_drawdown_pct"]),
        aggressiveness           = float(base["aggressiveness"]),
        risk_category            = cat,
        risk_score               = score,
    )
