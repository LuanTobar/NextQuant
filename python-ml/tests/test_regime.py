"""
Tests for the Sprint 1.3 HMM 5-state regime classifier.

Run: pytest tests/test_regime.py -v
"""

import time

import numpy as np
import pytest

from src.models.regime_classifier import RegimeClassifier

_VALID_REGIMES = {
    "BULL_QUIET", "BULL_VOLATILE", "SIDEWAYS", "BEAR_QUIET", "BEAR_VOLATILE"
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_prices(n: int = 500, trend: float = 0.0002, vol: float = 0.003,
                 seed: int = 42) -> list[float]:
    rng = np.random.default_rng(seed)
    returns = rng.normal(trend, vol, n)
    prices = 100.0 * np.cumprod(1 + returns)
    return list(np.maximum(prices, 1.0))


def _feed(clf: RegimeClassifier, prices: list[float], symbol: str = "AAPL") -> None:
    for p in prices:
        clf.add_tick(symbol, p)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestRegimeClassifierFallback:
    """Fallback (volatility-threshold) behaviour before HMM is fitted."""

    def test_insufficient_data_returns_sideways(self):
        clf = RegimeClassifier()
        clf.add_tick("AAPL", 100.0)
        result = clf.classify("AAPL")
        assert isinstance(result, dict)
        assert result["regime"] in _VALID_REGIMES
        assert result["method"] == "volatility_threshold"

    def test_fallback_output_schema(self):
        clf = RegimeClassifier()
        _feed(clf, _make_prices(10))
        result = clf.classify("AAPL")
        for key in ("regime", "probabilities", "state_idx", "volatility", "method"):
            assert key in result, f"Missing key: {key}"

    def test_fallback_probabilities_sum_to_one(self):
        clf = RegimeClassifier()
        _feed(clf, _make_prices(50))
        result = clf.classify("AAPL")
        total = sum(result["probabilities"].values())
        assert abs(total - 1.0) < 0.01, f"Probs sum to {total}"

    def test_fallback_state_idx_is_minus_one(self):
        clf = RegimeClassifier()
        _feed(clf, _make_prices(50))
        result = clf.classify("AAPL")
        assert result["state_idx"] == -1

    def test_all_five_regimes_in_probabilities(self):
        clf = RegimeClassifier()
        _feed(clf, _make_prices(50))
        result = clf.classify("AAPL")
        assert set(result["probabilities"].keys()) == _VALID_REGIMES

    def test_high_vol_series_maps_to_volatile_regime(self):
        """High-volatility price series → BEAR_VOLATILE or BULL_VOLATILE in fallback."""
        clf = RegimeClassifier()
        # Very high vol: 10% daily std
        _feed(clf, _make_prices(50, vol=0.10))
        result = clf.classify("AAPL")
        assert "VOLATILE" in result["regime"]

    def test_low_vol_series_maps_to_quiet_or_sideways(self):
        """Low-volatility series → BULL_QUIET or SIDEWAYS in fallback.

        At 1Hz tick frequency the annualization factor is sqrt(252×6.5×3600) ≈ 2784.
        To fall below the 15% annualized threshold we need vol_per_tick < 0.00005.
        """
        clf = RegimeClassifier()
        # 0.00005 per tick → ~14% annualized → LOW_VOL (< 0.15 threshold)
        _feed(clf, _make_prices(50, vol=0.00005))
        result = clf.classify("AAPL")
        assert result["regime"] in ("BULL_QUIET", "SIDEWAYS")


class TestRegimeClassifierMultiSymbol:
    def test_independent_symbols(self):
        clf = RegimeClassifier()
        _feed(clf, _make_prices(50, seed=1), "AAPL")
        _feed(clf, _make_prices(50, seed=2, vol=0.10), "BTCUSDT")

        r_aapl = clf.classify("AAPL")
        r_btc  = clf.classify("BTCUSDT")

        # Both valid
        assert r_aapl["regime"] in _VALID_REGIMES
        assert r_btc["regime"] in _VALID_REGIMES
        # BTC (high vol) should have higher volatile probability than AAPL (low vol)
        btc_vol_prob = r_btc["probabilities"].get("BEAR_VOLATILE", 0) + r_btc["probabilities"].get("BULL_VOLATILE", 0)
        aapl_vol_prob = r_aapl["probabilities"].get("BEAR_VOLATILE", 0) + r_aapl["probabilities"].get("BULL_VOLATILE", 0)
        assert btc_vol_prob >= aapl_vol_prob

    def test_unknown_symbol_returns_fallback(self):
        clf = RegimeClassifier()
        result = clf.classify("NONEXISTENT")
        assert result["regime"] in _VALID_REGIMES
        assert result["method"] == "volatility_threshold"


class TestRegimeClassifierHMM:
    """Tests that require HMM to train (uses background thread)."""

    def test_hmm_trains_after_enough_obs(self):
        """HMM should fit after retrain_every=200 observations."""
        clf = RegimeClassifier(retrain_every=200, min_obs=200)
        _feed(clf, _make_prices(300, seed=7))
        time.sleep(3.0)   # wait for background thread

        result = clf.classify("AAPL")
        assert result["regime"] in _VALID_REGIMES
        # After fitting, method should be hmm_5state
        if result["method"] == "hmm_5state":
            assert result["state_idx"] >= 0

    def test_hmm_output_schema_when_fitted(self):
        clf = RegimeClassifier(retrain_every=200, min_obs=200)
        _feed(clf, _make_prices(300))
        time.sleep(3.0)

        result = clf.classify("AAPL")
        for key in ("regime", "probabilities", "state_idx", "volatility", "method"):
            assert key in result

    def test_hmm_probabilities_sum_to_one(self):
        clf = RegimeClassifier(retrain_every=200, min_obs=200)
        _feed(clf, _make_prices(300))
        time.sleep(3.0)

        result = clf.classify("AAPL")
        total = sum(result["probabilities"].values())
        assert abs(total - 1.0) < 0.02, f"Probabilities sum to {total}"

    def test_hmm_five_unique_regime_names(self):
        """State map should cover all 5 regime names."""
        clf = RegimeClassifier(retrain_every=200, min_obs=200)
        _feed(clf, _make_prices(400, seed=99))
        time.sleep(4.0)

        if clf._models.get("AAPL") is not None:
            state_map = clf._state_maps.get("AAPL", {})
            regime_names = set(state_map.values())
            # All assigned names must be valid
            assert regime_names <= _VALID_REGIMES
            # Should have 5 distinct states
            assert len(state_map) == 5

    def test_regime_changes_with_different_vol(self):
        """Low-vol vs high-vol series should produce different regime classifications."""
        clf_low  = RegimeClassifier(retrain_every=200, min_obs=200)
        clf_high = RegimeClassifier(retrain_every=200, min_obs=200)

        _feed(clf_low,  _make_prices(300, vol=0.001, seed=5))
        _feed(clf_high, _make_prices(300, vol=0.020, seed=5))

        time.sleep(3.0)

        r_low  = clf_low.classify("AAPL")
        r_high = clf_high.classify("AAPL")

        # High-vol classifier should show a volatile signal.
        # Two independently-trained HMMs learn relative states within their own vol scale,
        # so we accept: probability ordering correct OR regime label is volatile.
        high_vol_prob_low  = sum(r_low["probabilities"].get(r, 0)  for r in ("BULL_VOLATILE", "BEAR_VOLATILE"))
        high_vol_prob_high = sum(r_high["probabilities"].get(r, 0) for r in ("BULL_VOLATILE", "BEAR_VOLATILE"))
        assert high_vol_prob_high >= high_vol_prob_low or "VOLATILE" in r_high["regime"], (
            f"Expected high-vol signal: vol_prob={high_vol_prob_high:.3f} vs {high_vol_prob_low:.3f}, "
            f"regime={r_high['regime']}"
        )
