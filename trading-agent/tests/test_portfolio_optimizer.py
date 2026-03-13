"""
Tests for PortfolioOptimizer — Half-Kelly + regime + concentration.

Run: .venv/Scripts/python.exe -m pytest tests/test_portfolio_optimizer.py -v
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock
import pytest

from src.portfolio_optimizer import (
    PortfolioOptimizer,
    MIN_FRACTION,
    MAX_FRACTION,
    HALF_KELLY,
    MIN_TRADES,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_score(
    win_rate: float = 0.6,
    avg_win: float = 0.02,
    avg_loss: float = 0.01,
    total_trades: int = 10,
):
    score = MagicMock()
    score.win_rate      = win_rate
    score.avg_win_pct   = avg_win
    score.avg_loss_pct  = -avg_loss   # stored as negative in SymbolScore
    score.total_trades  = total_trades
    return score


def _make_position(market_value: float = 100.0):
    pos = MagicMock()
    pos.market_value = market_value
    return pos


_optimizer = PortfolioOptimizer()


# ── TestKellyFraction ─────────────────────────────────────────────────────────

class TestKellyFraction:
    def test_known_inputs_W60_R2(self):
        # W=0.6, avg_win=0.02, avg_loss=0.01 → b=2, f=0.6-0.4/2=0.40, half=0.20
        score = _make_score(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert abs(frac - 0.20) < 0.001

    def test_known_inputs_W55_R15(self):
        # W=0.55, avg_win=0.015, avg_loss=0.010 → b=1.5, f=0.55-0.45/1.5=0.25, half=0.125
        score = _make_score(win_rate=0.55, avg_win=0.015, avg_loss=0.010)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert abs(frac - 0.125) < 0.001

    def test_none_score_returns_fallback(self):
        frac = PortfolioOptimizer._kelly_fraction(None)
        assert frac == 0.25

    def test_insufficient_trades_returns_fallback(self):
        score = _make_score(total_trades=MIN_TRADES - 1)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert frac == 0.25

    def test_exactly_min_trades_uses_kelly(self):
        score = _make_score(win_rate=0.6, avg_win=0.02, avg_loss=0.01,
                             total_trades=MIN_TRADES)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert abs(frac - 0.20) < 0.001  # Kelly active, not fallback

    def test_negative_kelly_clamped_to_zero_times_half(self):
        # W=0.2, avg_win=0.005, avg_loss=0.02 → b=0.25, f=0.2-0.8/0.25=-3.0 → clamped to 0
        score = _make_score(win_rate=0.2, avg_win=0.005, avg_loss=0.02, total_trades=10)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert frac == 0.0  # max(0, -3.0) * 0.5

    def test_perfect_win_rate_capped_at_max(self):
        # W=1.0, any positive R → Kelly=1.0, half=0.5 (not capped)
        score = _make_score(win_rate=1.0, avg_win=0.05, avg_loss=0.01, total_trades=10)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert 0.0 < frac <= MAX_FRACTION

    def test_zero_avg_loss_returns_fallback(self):
        score = _make_score(avg_loss=0.0, total_trades=10)
        frac = PortfolioOptimizer._kelly_fraction(score)
        assert frac == 0.25


# ── TestRegimeMultiplier ──────────────────────────────────────────────────────

class TestRegimeMultiplier:
    @pytest.mark.parametrize("regime,expected", [
        ("BULL_QUIET",    1.00),
        ("BULL_VOLATILE", 0.70),
        ("SIDEWAYS",      0.60),
        ("BEAR_QUIET",    0.40),
        ("BEAR_VOLATILE", 0.25),
    ])
    def test_exact_regimes(self, regime, expected):
        assert PortfolioOptimizer._regime_multiplier(regime) == expected

    def test_unknown_regime_returns_default(self):
        assert PortfolioOptimizer._regime_multiplier("UNKNOWN") == 0.60

    def test_empty_string_returns_default(self):
        assert PortfolioOptimizer._regime_multiplier("") == 0.60

    def test_case_insensitive(self):
        assert PortfolioOptimizer._regime_multiplier("bear_volatile") == 0.25

    def test_partial_match_volatile(self):
        # "VOLATILE" alone doesn't match any full key (keys are substrings of input,
        # not the other way around) → returns default SIDEWAYS equivalent
        mult = PortfolioOptimizer._regime_multiplier("VOLATILE")
        assert mult == 0.60  # default


# ── TestConcentrationPenalty ──────────────────────────────────────────────────

class TestConcentrationPenalty:
    def test_no_positions(self):
        assert PortfolioOptimizer._concentration_penalty([]) == 1.00

    def test_one_real_position(self):
        pos = [_make_position(100.0)]
        assert PortfolioOptimizer._concentration_penalty(pos) == 0.85

    def test_two_real_positions(self):
        pos = [_make_position(100.0), _make_position(200.0)]
        assert PortfolioOptimizer._concentration_penalty(pos) == 0.70

    def test_three_real_positions(self):
        pos = [_make_position(100.0), _make_position(200.0), _make_position(50.0)]
        assert PortfolioOptimizer._concentration_penalty(pos) == 0.70

    def test_dust_positions_ignored(self):
        # market_value <= $1 → dust → ignored
        pos = [_make_position(0.5), _make_position(0.1)]
        assert PortfolioOptimizer._concentration_penalty(pos) == 1.00

    def test_mixed_dust_and_real(self):
        pos = [_make_position(0.5), _make_position(100.0)]
        assert PortfolioOptimizer._concentration_penalty(pos) == 0.85


# ── TestOptimizeFull ─────────────────────────────────────────────────────────

class TestOptimizeFull:
    def test_bull_quiet_no_positions_with_history(self):
        # Kelly=0.20, regime=1.0, conc=1.0 → 0.20
        score = _make_score(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        frac, meta = _optimizer.optimize("AAPL", "BULL_QUIET", score, [])
        assert abs(frac - 0.20) < 0.001
        assert meta["kelly_base"] == 0.20
        assert meta["regime_mult"] == 1.00
        assert meta["conc_penalty"] == 1.00
        assert meta["final_fraction"] == round(frac, 3)

    def test_bear_volatile_two_positions_with_history(self):
        # Kelly=0.20, regime=0.25, conc=0.70 → 0.20*0.25*0.70=0.035 → clamped to MIN=0.05
        score = _make_score(win_rate=0.6, avg_win=0.02, avg_loss=0.01)
        pos = [_make_position(100.0), _make_position(200.0)]
        frac, meta = _optimizer.optimize("AAPL", "BEAR_VOLATILE", score, pos)
        assert frac == MIN_FRACTION  # 0.035 < 0.05, so clamped

    def test_no_history_fallback_sideways(self):
        # Kelly=0.25 (fallback), regime=0.60, conc=1.0 → 0.15
        frac, meta = _optimizer.optimize("AAPL", "SIDEWAYS", None, [])
        assert abs(frac - 0.15) < 0.001
        assert meta["kelly_base"] == 0.25

    def test_min_fraction_enforced(self):
        # Very bad history: negative Kelly → fraction should be MIN_FRACTION
        score = _make_score(win_rate=0.1, avg_win=0.001, avg_loss=0.05)
        frac, _ = _optimizer.optimize("AAPL", "BEAR_VOLATILE", score, [])
        assert frac >= MIN_FRACTION

    def test_max_fraction_never_exceeded(self):
        # Best case: high win rate, bull quiet, no positions
        score = _make_score(win_rate=0.9, avg_win=0.10, avg_loss=0.01, total_trades=50)
        frac, _ = _optimizer.optimize("AAPL", "BULL_QUIET", score, [])
        assert frac <= MAX_FRACTION

    def test_metadata_keys_present(self):
        frac, meta = _optimizer.optimize("BTC", "SIDEWAYS", None, [])
        assert "kelly_base" in meta
        assert "regime_mult" in meta
        assert "conc_penalty" in meta
        assert "final_fraction" in meta
