"""
Trading strategies for the backtesting engine.

All strategies implement the Strategy ABC:

    on_bar(bar: dict, features: dict) -> dict
        {"action": "BUY" | "SELL" | "HOLD", "size": float}

``size`` ∈ [0, 1] — fraction of available cash to allocate.

Strategies are stateful: create a **new instance per backtest run**
to avoid contamination across runs.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class Strategy(ABC):
    """Abstract base class for all backtesting strategies."""

    @abstractmethod
    def on_bar(self, bar: dict, features: dict) -> dict:
        """
        Process one bar and return a trading signal.

        Args:
            bar:      Current OHLCV tick dict (live-system format).
            features: Pre-computed FeatureStore features (may be empty).
                      NexQuantStrategy computes its own features internally.

        Returns:
            {"action": "BUY" | "SELL" | "HOLD", "size": float}
        """
        ...

    def name(self) -> str:
        return self.__class__.__name__


# ── Baselines ──────────────────────────────────────────────────────────────────

class BuyAndHoldStrategy(Strategy):
    """
    Buy on the first bar and hold until the end.

    Serves as the passive benchmark; any active strategy
    that doesn't consistently beat this is not adding value.
    """

    def __init__(self) -> None:
        self._bought = False

    def on_bar(self, bar: dict, features: dict) -> dict:
        if not self._bought:
            self._bought = True
            return {"action": "BUY", "size": 1.0}
        return {"action": "HOLD", "size": 0.0}


class RandomStrategy(Strategy):
    """
    Uniformly random BUY / SELL / HOLD each bar.

    Serves as a statistical noise baseline.  Expected Sharpe ≈ 0.
    """

    def __init__(
        self,
        seed: int = 42,
        buy_prob: float = 0.25,
        sell_prob: float = 0.25,
    ) -> None:
        self._rng       = np.random.default_rng(seed)
        self._buy_prob  = buy_prob
        self._sell_prob = sell_prob

    def on_bar(self, bar: dict, features: dict) -> dict:
        r = float(self._rng.random())
        if r < self._buy_prob:
            return {"action": "BUY",  "size": 1.0}
        if r < self._buy_prob + self._sell_prob:
            return {"action": "SELL", "size": 1.0}
        return {"action": "HOLD", "size": 0.0}


# ── Full ML pipeline ───────────────────────────────────────────────────────────

class NexQuantStrategy(Strategy):
    """
    Full NexQuant ML pipeline strategy.

    Orchestrates the same components as the live MLService:
      - FeatureStore       (technical + microstructure features)
      - RegimeClassifier   (HMM 5-state regime)
      - CausalAnalyzer     (Granger + TE causal alpha)
      - EnsemblePredictor  (LGBM + LSTM + GARCH stacking)

    Signal logic (mirrors live _generate_signal + ensemble branch):
      - When ensemble is trained: use ensemble signal + causal adjustment
      - Before ensemble training: momentum fallback
      - VOLATILE regime → higher entry threshold (0.4% vs 0.2%)

    Create a new instance per backtest run.
    """

    def __init__(
        self,
        lookback: int = 100,
        analyze_every: int = 50,
        lgbm_retrain_every: int = 300,
        horizon_bars: int = 10,
    ) -> None:
        from src.features import FeatureStore
        from src.models.regime_classifier import RegimeClassifier
        from src.models.causal_analyzer import CausalAnalyzer
        from src.models.ensemble import EnsemblePredictor

        # cache_ttl_s=0: always recompute (no stale cache in backtests)
        self._feature_store = FeatureStore(cache_ttl_s=0.0)
        self._regime        = RegimeClassifier(window=20)
        self._causal        = CausalAnalyzer(
            lookback=lookback, analyze_every=analyze_every
        )
        self._ensemble = EnsemblePredictor(
            lgbm_kwargs={"retrain_every": lgbm_retrain_every, "horizon_bars": horizon_bars},
            lstm_kwargs={"retrain_every": lgbm_retrain_every * 2, "horizon_bars": horizon_bars},
            meta_retrain_every=lgbm_retrain_every // 2,
            horizon_bars=horizon_bars,
        )
        self._prev_close: float | None = None

    def on_bar(self, bar: dict, features: dict) -> dict:
        symbol   = bar.get("symbol", "AAPL")
        exchange = bar.get("exchange", "US")
        close    = float(bar.get("close", 0.0))
        key      = f"{exchange}:{symbol}"

        # Feed all pipeline components
        self._feature_store.add_tick(bar)
        self._regime.add_tick(key, close)
        self._causal.add_tick(bar)

        # Compute features and feed ensemble
        computed = self._feature_store.compute_features(exchange, symbol)
        if computed:
            self._ensemble.observe(close, computed)
        ensemble_result = self._ensemble.predict(computed or {})

        # Context signals
        regime_result = self._regime.classify(key)
        causal_result = self._causal.analyze(symbol, exchange)
        vol_regime    = regime_result.get("regime", "SIDEWAYS")
        causal_alpha  = causal_result.get("alpha_signal", 0.0)

        # Signal generation
        if ensemble_result["is_trained"]:
            expected_return = ensemble_result["expected_return"] + 0.1 * causal_alpha
            signal          = ensemble_result["signal"]
            confidence      = ensemble_result["confidence"]
        else:
            # Momentum fallback
            if self._prev_close and self._prev_close > 0:
                expected_return = (close - self._prev_close) / self._prev_close
            else:
                expected_return = 0.0
            signal     = "HOLD"
            confidence = 0.0

        self._prev_close = close

        # Higher threshold in volatile regimes
        threshold = 0.004 if "VOLATILE" in vol_regime else 0.002

        if expected_return > threshold or signal == "BUY":
            size = min(1.0, 0.5 + 0.5 * confidence)
            return {"action": "BUY",  "size": size}
        if expected_return < -threshold or signal == "SELL":
            return {"action": "SELL", "size": 1.0}
        return {"action": "HOLD", "size": 0.0}
