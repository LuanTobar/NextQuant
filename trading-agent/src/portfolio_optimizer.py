"""
Portfolio Optimizer — Half-Kelly criterion + regime dampening + concentration penalty.

Replaces the flat aggressiveness multiplier in RiskManager with a data-driven
sizing fraction derived from:
  1. Half-Kelly from historical per-symbol accuracy (SymbolScore)
  2. Regime-aware dampening (5-state HMM labels → multiplier)
  3. Portfolio concentration penalty (too many open positions → reduce)

Output: a fraction ∈ [MIN_FRACTION, MAX_FRACTION] fed into
RiskManager.calculate_position_size() as `kelly_fraction`.
"""

from __future__ import annotations

import structlog

from .score_tracker import SymbolScore
from .brokers.base import Position

logger = structlog.get_logger()

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_FRACTION = 0.05   # never size below 5% of max_position_size_usd
MAX_FRACTION = 1.00   # never exceed 100%
HALF_KELLY   = 0.50   # conservative half-Kelly multiplier
MIN_TRADES   = 5      # minimum trades before trusting Kelly; fallback below

# Maps 5-state HMM regime labels → sizing multiplier.
# Substring match so "BULL_VOLATILE" matches the key "BULL_VOLATILE".
_REGIME_MULTIPLIERS: dict[str, float] = {
    "BULL_QUIET":    1.00,
    "BULL_VOLATILE": 0.70,
    "SIDEWAYS":      0.60,
    "BEAR_QUIET":    0.40,
    "BEAR_VOLATILE": 0.25,
}
_DEFAULT_REGIME_MULT = 0.60   # SIDEWAYS-equivalent for unknown regimes


class PortfolioOptimizer:
    """
    Computes an optimal position-size fraction [MIN_FRACTION, MAX_FRACTION].

    All methods are pure / stateless — safe to call concurrently across users.
    """

    def optimize(
        self,
        symbol: str,
        regime: str,
        score: SymbolScore | None,
        open_positions: list[Position],
    ) -> tuple[float, dict]:
        """
        Return (fraction, metadata).

        fraction  — multiply max_position_size_usd by this value.
        metadata  — logging dict with per-component values.
        """
        kelly_base   = self._kelly_fraction(score)
        regime_mult  = self._regime_multiplier(regime)
        conc_penalty = self._concentration_penalty(open_positions)

        raw      = kelly_base * regime_mult * conc_penalty
        fraction = max(MIN_FRACTION, min(MAX_FRACTION, raw))

        meta = {
            "kelly_base":     round(kelly_base, 3),
            "regime_mult":    regime_mult,
            "conc_penalty":   round(conc_penalty, 3),
            "final_fraction": round(fraction, 3),
        }
        logger.debug(
            "Portfolio optimizer",
            symbol=symbol, regime=regime,
            open_positions=len([p for p in open_positions if p.market_value > 1.0]),
            **meta,
        )
        return fraction, meta

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _kelly_fraction(score: SymbolScore | None) -> float:
        """
        Compute half-Kelly sizing fraction from historical accuracy.

        Formula:
            b = avg_win_pct / avg_loss_pct       (reward/risk ratio)
            f_kelly = W - (1 - W) / b            (Kelly criterion)
            f_half  = max(0, f_kelly) * HALF_KELLY

        Returns fallback 0.25 when insufficient history.
        """
        if score is None or score.total_trades < MIN_TRADES:
            return 0.25  # conservative fallback

        W        = score.win_rate
        avg_win  = score.avg_win_pct
        avg_loss = abs(score.avg_loss_pct)

        if avg_loss < 1e-6 or W <= 0:
            return 0.25

        b = avg_win / avg_loss
        if b <= 0:
            return MIN_FRACTION

        f_kelly = W - (1.0 - W) / b
        f_kelly = max(0.0, f_kelly)      # negative Kelly → no edge, use minimum
        return min(f_kelly * HALF_KELLY, MAX_FRACTION)

    @staticmethod
    def _regime_multiplier(regime: str) -> float:
        """
        Map 5-state HMM regime label to a sizing multiplier.
        Uses substring match so partial labels (e.g., "VOLATILE") also work.
        """
        regime_upper = regime.upper()
        for key, mult in _REGIME_MULTIPLIERS.items():
            if key in regime_upper:
                return mult
        return _DEFAULT_REGIME_MULT

    @staticmethod
    def _concentration_penalty(open_positions: list[Position]) -> float:
        """
        Reduce sizing when the portfolio is already concentrated.

        Only counts non-dust positions (market_value > $1).
        Penalty tiers:
          0 positions → 1.00 (no penalty)
          1 position  → 0.85 (mild penalty)
          2+ positions → 0.70 (stronger penalty, encourages diversification)
        """
        non_dust = sum(1 for p in open_positions if p.market_value > 1.0)
        if non_dust == 0:
            return 1.00
        if non_dust == 1:
            return 0.85
        return 0.70
