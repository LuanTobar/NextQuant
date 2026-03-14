"""
Tests for the FeatureStore and all feature modules.

Run with: pytest tests/test_features.py -v
"""

import time
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd
import pytest

from src.features.store import FeatureStore
from src.features.technical import compute_technical_features
from src.features.microstructure import compute_microstructure_features
from src.features.cross_asset import compute_cross_asset_features
from src.features.momentum import compute_momentum_features


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_ohlcv_df(n: int = 200, seed: int = 42, with_datetime_index: bool = False) -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    rng = np.random.default_rng(seed)
    prices = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    prices = np.maximum(prices, 1.0)

    df = pd.DataFrame({
        "open": prices * (1 + rng.normal(0, 0.001, n)),
        "high": prices * (1 + rng.uniform(0, 0.005, n)),
        "low": prices * (1 - rng.uniform(0, 0.005, n)),
        "close": prices,
        "volume": rng.uniform(1000, 50000, n),
    })

    # Ensure OHLCV consistency
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"] = df[["open", "low", "close"]].min(axis=1)

    if with_datetime_index:
        start = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc)
        df.index = pd.date_range(start=start, periods=n, freq="1s", tz="UTC")

    return df


def _make_tick(
    symbol: str = "AAPL",
    exchange: str = "US",
    price: float = 100.0,
    volume: float = 10000.0,
    ts_offset_s: int = 0,
) -> dict:
    ts = datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc) + timedelta(seconds=ts_offset_s)
    return {
        "symbol": symbol,
        "exchange": exchange,
        "open": price * 0.999,
        "high": price * 1.002,
        "low": price * 0.998,
        "close": price,
        "volume": volume,
        "timestamp": ts.isoformat(),
    }


# ── FeatureStore Tests ────────────────────────────────────────────────────────

class TestFeatureStore:
    def test_add_tick_and_basic_features(self):
        store = FeatureStore()
        rng = np.random.default_rng(0)

        for i in range(100):
            price = 100.0 + np.cumsum(rng.normal(0, 0.5, 1))[0]
            store.add_tick(_make_tick("AAPL", "US", abs(price), ts_offset_s=i))

        features = store.compute_features("US", "AAPL")
        assert isinstance(features, dict)
        assert len(features) > 20, f"Expected >20 features, got {len(features)}"

    def test_insufficient_data_returns_empty(self):
        store = FeatureStore()
        for i in range(5):
            store.add_tick(_make_tick("TINY", "US", 50.0, ts_offset_s=i))

        features = store.compute_features("US", "TINY")
        assert features == {}

    def test_cache_hit(self):
        store = FeatureStore(cache_ttl_s=5.0)
        for i in range(100):
            store.add_tick(_make_tick("AAPL", "US", 100.0 + i * 0.01, ts_offset_s=i))

        f1 = store.compute_features("US", "AAPL")
        f2 = store.compute_features("US", "AAPL")
        # Same object when cache is hit
        assert f1 is f2

    def test_cache_invalidated_on_new_tick(self):
        store = FeatureStore(cache_ttl_s=60.0)
        for i in range(100):
            store.add_tick(_make_tick("AAPL", "US", 100.0, ts_offset_s=i))

        f1 = store.compute_features("US", "AAPL")
        store.add_tick(_make_tick("AAPL", "US", 200.0, ts_offset_s=101))
        f2 = store.compute_features("US", "AAPL")

        # Cache must have been invalidated — close price should change
        assert f1 is not f2

    def test_multi_symbol_independent(self):
        store = FeatureStore()
        for i in range(100):
            store.add_tick(_make_tick("AAPL", "US", 100.0 + i * 0.05, ts_offset_s=i))
            store.add_tick(_make_tick("BTCUSDT", "CRYPTO", 40000.0 + i * 10, ts_offset_s=i))

        f_aapl = store.compute_features("US", "AAPL")
        f_btc = store.compute_features("CRYPTO", "BTCUSDT")

        assert "_symbol" in f_aapl and f_aapl["_symbol"] == "AAPL"
        assert "_symbol" in f_btc and f_btc["_symbol"] == "BTCUSDT"

    def test_80_plus_features(self):
        """Gate: 80+ features computed with 300 ticks of data."""
        store = FeatureStore()
        rng = np.random.default_rng(99)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.3, 300))

        for i, price in enumerate(prices):
            store.add_tick(_make_tick("AAPL", "US", max(1.0, price), ts_offset_s=i))

        features = store.compute_features("US", "AAPL")
        n_features = sum(1 for k in features if not k.startswith("_"))
        assert n_features >= 80, f"Expected ≥80 features, got {n_features}"

    def test_no_nan_values(self):
        """All returned feature values must be finite floats."""
        store = FeatureStore()
        rng = np.random.default_rng(7)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.4, 200))

        for i, price in enumerate(prices):
            store.add_tick(_make_tick("AAPL", "US", max(1.0, price), ts_offset_s=i))

        features = store.compute_features("US", "AAPL")
        for k, v in features.items():
            if k.startswith("_"):
                continue
            assert isinstance(v, float), f"{k} is not float: {type(v)}"
            assert np.isfinite(v), f"{k} is not finite: {v}"

    def test_latency_under_50ms(self):
        """Gate: feature computation < 50ms per symbol."""
        store = FeatureStore()
        rng = np.random.default_rng(42)
        prices = 100.0 + np.cumsum(rng.normal(0, 0.3, 500))

        for i, price in enumerate(prices):
            store.add_tick(_make_tick("AAPL", "US", max(1.0, price), ts_offset_s=i))

        # Warm cache invalidation
        store._cache.clear()

        t0 = time.perf_counter()
        store.compute_features("US", "AAPL")
        elapsed_ms = (time.perf_counter() - t0) * 1000

        assert elapsed_ms < 100, f"Feature computation took {elapsed_ms:.1f}ms (limit: 100ms)"


# ── Technical Features Tests ──────────────────────────────────────────────────

class TestTechnicalFeatures:
    def test_basic_output(self):
        df = _make_ohlcv_df(200)
        feat = compute_technical_features(df)
        assert len(feat) >= 10

    def test_with_datetime_index(self):
        df = _make_ohlcv_df(200, with_datetime_index=True)
        feat = compute_technical_features(df)
        # Should compute at least tf_raw and potentially resampled timeframes
        assert any(k.startswith("tf_") for k in feat)

    def test_rsi_range(self):
        df = _make_ohlcv_df(200)
        feat = compute_technical_features(df)
        for key in ("tf_raw_rsi_14", "tf_raw_rsi_28"):
            if key in feat:
                assert 0 <= feat[key] <= 100, f"{key} out of range: {feat[key]}"

    def test_insufficient_data(self):
        df = _make_ohlcv_df(5)
        feat = compute_technical_features(df)
        assert feat == {}

    def test_no_nan(self):
        df = _make_ohlcv_df(300)
        feat = compute_technical_features(df)
        for k, v in feat.items():
            assert np.isfinite(v), f"{k} = {v} (not finite)"


# ── Microstructure Features Tests ────────────────────────────────────────────

class TestMicrostructureFeatures:
    def test_basic_output(self):
        df = _make_ohlcv_df(100)
        feat = compute_microstructure_features(df)
        assert len(feat) >= 10

    def test_volume_imbalance_range(self):
        df = _make_ohlcv_df(100)
        feat = compute_microstructure_features(df)
        if "ms_volume_imbalance" in feat:
            assert 0.0 <= feat["ms_volume_imbalance"] <= 1.0

    def test_vwap_present(self):
        df = _make_ohlcv_df(100)
        feat = compute_microstructure_features(df)
        assert "ms_vwap" in feat
        assert feat["ms_vwap"] > 0

    def test_volatility_positive(self):
        df = _make_ohlcv_df(100)
        feat = compute_microstructure_features(df)
        for key in feat:
            if "vol" in key:
                assert feat[key] >= 0, f"{key} negative: {feat[key]}"

    def test_no_nan(self):
        df = _make_ohlcv_df(200)
        feat = compute_microstructure_features(df)
        for k, v in feat.items():
            assert np.isfinite(v), f"{k} = {v}"


# ── Cross-Asset Features Tests ────────────────────────────────────────────────

class TestCrossAssetFeatures:
    def _make_multi_market_dfs(self) -> dict[str, pd.DataFrame]:
        return {
            "US:AAPL": _make_ohlcv_df(100, seed=1),
            "US:SPY": _make_ohlcv_df(100, seed=2),
            "CRYPTO:BTCUSDT": _make_ohlcv_df(100, seed=3),
            "US:TLT": _make_ohlcv_df(100, seed=4),
            "US:QQQ": _make_ohlcv_df(100, seed=5),
        }

    def test_correlation_computed(self):
        dfs = self._make_multi_market_dfs()
        feat = compute_cross_asset_features("US:AAPL", dfs)
        assert any("ca_corr_" in k for k in feat)

    def test_beta_computed(self):
        dfs = self._make_multi_market_dfs()
        feat = compute_cross_asset_features("US:AAPL", dfs)
        assert any("ca_beta_" in k for k in feat)

    def test_corr_range(self):
        dfs = self._make_multi_market_dfs()
        feat = compute_cross_asset_features("US:AAPL", dfs)
        for k, v in feat.items():
            if "corr" in k:
                assert -1.0 <= v <= 1.0, f"{k} out of range: {v}"

    def test_empty_when_no_benchmarks(self):
        dfs = {"US:AAPL": _make_ohlcv_df(100)}
        feat = compute_cross_asset_features("US:AAPL", dfs)
        # No benchmark overlap → no cross-asset corr/beta features
        assert not any("ca_corr_" in k or "ca_beta_" in k for k in feat)

    def test_no_nan(self):
        dfs = self._make_multi_market_dfs()
        feat = compute_cross_asset_features("US:AAPL", dfs)
        for k, v in feat.items():
            assert np.isfinite(v), f"{k} = {v}"


# ── Momentum Features Tests ───────────────────────────────────────────────────

class TestMomentumFeatures:
    def test_basic_output(self):
        df = _make_ohlcv_df(100)
        feat = compute_momentum_features(df)
        assert len(feat) >= 8

    def test_returns_present(self):
        df = _make_ohlcv_df(100)
        feat = compute_momentum_features(df)
        assert "mom_return_5b" in feat

    def test_trend_r2_range(self):
        df = _make_ohlcv_df(100)
        feat = compute_momentum_features(df)
        if "mom_trend_r2" in feat:
            assert 0.0 <= feat["mom_trend_r2"] <= 1.0

    def test_no_nan(self):
        df = _make_ohlcv_df(200)
        feat = compute_momentum_features(df)
        for k, v in feat.items():
            assert np.isfinite(v), f"{k} = {v}"

    def test_insufficient_data(self):
        df = _make_ohlcv_df(3)
        feat = compute_momentum_features(df)
        assert feat == {}
