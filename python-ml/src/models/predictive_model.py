"""
PredictiveModel — backward-compatible price predictor.

Exposes the same legacy API (add_tick / predict) while delegating to
EnsemblePredictor when FeatureStore features are supplied via add_features().

Legacy output (always available):
  {
    "predicted_close": float,
    "confidence_low":  float,
    "confidence_high": float,
    "method":          "ensemble_*" | "ema_momentum" | "insufficient_data",
  }

Sprint 1.2 extension:
  Call add_features(symbol, close, features) from on_snapshot once the
  FeatureStore has computed its output — the ensemble trains incrementally
  and predict() switches to ensemble output once trained.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()


class PredictiveModel:
    """
    EMA+momentum baseline with optional EnsemblePredictor delegation.

    When add_features() is called with FeatureStore output, an internal
    per-symbol EnsemblePredictor is created and trained incrementally.
    predict() returns ensemble-based output once trained; falls back to
    EMA+momentum otherwise — keeping all downstream callers unaffected.
    """

    def __init__(self, window: int = 20):
        self.window = window
        self.history: dict[str, list[float]] = {}
        # Sprint 1.2: per-symbol ensemble predictors (lazy-initialised)
        self._ensembles: dict[str, object] = {}
        self._last_features: dict[str, dict] = {}

    # ── Legacy API (unchanged) ─────────────────────────────────────────────

    def add_tick(self, symbol: str, close: float) -> None:
        """Buffer a price tick for the EMA baseline."""
        if symbol not in self.history:
            self.history[symbol] = []
        self.history[symbol].append(close)
        if len(self.history[symbol]) > 200:
            self.history[symbol] = self.history[symbol][-200:]

    def predict(self, symbol: str) -> dict:
        """
        Return predicted_close + confidence interval.

        Uses the ensemble when trained; falls back to EMA+momentum.
        """
        ensemble = self._ensembles.get(symbol)
        features = self._last_features.get(symbol)
        prices = self.history.get(symbol, [])
        current = float(prices[-1]) if prices else 0.0

        if ensemble is not None and features and ensemble.is_trained:  # type: ignore[union-attr]
            try:
                res = ensemble.predict(features)  # type: ignore[union-attr]
                er = res.get("expected_return", 0.0)
                return {
                    "predicted_close": round(current * (1.0 + er), 4),
                    "confidence_low":  round(current * (1.0 + res.get("ci_low", -0.01)), 4),
                    "confidence_high": round(current * (1.0 + res.get("ci_high",  0.01)), 4),
                    "method": f"ensemble_{res.get('method', 'unknown')}",
                }
            except Exception as e:
                logger.warning("Ensemble predict in wrapper failed", symbol=symbol, error=str(e))

        return self._ema_predict(symbol)

    # ── Sprint 1.2 extension ───────────────────────────────────────────────

    def add_features(self, symbol: str, close: float, features: dict) -> None:
        """
        Feed a tick with its FeatureStore feature dict to the ensemble.

        Safe to call on every snapshot even if torch / lightgbm are absent —
        the EnsemblePredictor degrades gracefully in that case.
        """
        if not features or close <= 0:
            return

        if symbol not in self._ensembles:
            # Lazy import so the module loads even without lightgbm/torch
            from src.models.ensemble import EnsemblePredictor
            self._ensembles[symbol] = EnsemblePredictor(
                lgbm_kwargs={"retrain_every": 500, "horizon_bars": 60},
                meta_retrain_every=200,
                horizon_bars=60,
            )
            logger.info("EnsemblePredictor created for symbol", symbol=symbol)

        self._ensembles[symbol].observe(close, features)  # type: ignore[union-attr]
        self._last_features[symbol] = features

    # ── Internal: EMA+momentum baseline ───────────────────────────────────

    def _ema_predict(self, symbol: str) -> dict:
        prices = self.history.get(symbol, [])

        if len(prices) < self.window:
            last = float(prices[-1]) if prices else 0.0
            return {
                "predicted_close": round(last, 2),
                "confidence_low":  round(last * 0.99, 2),
                "confidence_high": round(last * 1.01, 2),
                "method": "insufficient_data",
            }

        recent = np.array(prices[-self.window:])

        # Exponential moving average
        weights = np.exp(np.linspace(-1.0, 0.0, self.window))
        weights /= weights.sum()
        ema = float(np.dot(weights, recent))

        # Momentum: linear trend slope
        x = np.arange(self.window)
        slope = float(np.polyfit(x, recent, 1)[0])
        predicted = ema + slope

        # Confidence interval from recent volatility
        returns = np.diff(recent) / recent[:-1]
        vol = float(np.std(returns)) if len(returns) > 1 else 0.01
        std_price = float(recent[-1]) * vol

        return {
            "predicted_close": round(predicted, 2),
            "confidence_low":  round(predicted - 1.96 * std_price, 2),
            "confidence_high": round(predicted + 1.96 * std_price, 2),
            "method": "ema_momentum",
        }
