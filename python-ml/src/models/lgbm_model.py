"""
LightGBM binary direction classifier — UP/DOWN prediction.

Architecture:
  - Self-labeling streaming model: buffers observations and auto-labels
    them when `horizon_bars` ticks have elapsed (future return known).
  - Retrains every `retrain_every` new labeled observations.
  - Features: FeatureStore output (80+ numeric features).
  - Target: sign(price_at_t+horizon / price_at_t - 1) → 1=UP, 0=DOWN.

Output:
  {
    "direction": "UP" | "DOWN",
    "probability": float,           # P(UP), range [0, 1]
    "feature_importances": dict,    # top-10 by gain
    "labeled_count": int,
    "is_trained": bool,
  }
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()


class LGBMPredictor:
    """
    Streaming LightGBM binary direction classifier.

    Observes (timestamp, price, features) tuples. After `horizon_bars` ticks,
    labels old observations with the realized return direction and accumulates
    a training set. Retrains every `retrain_every` new labels.
    """

    def __init__(
        self,
        retrain_every: int = 500,
        horizon_bars: int = 60,        # label horizon in ticks (60s @ 1Hz = 1min)
        max_labeled: int = 5_000,
        n_estimators: int = 500,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        feature_fraction: float = 0.7,
    ):
        self.retrain_every = retrain_every
        self.horizon_bars = horizon_bars
        self.max_labeled = max_labeled
        self._lgbm_params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "feature_fraction": feature_fraction,
            "num_leaves": 31,
            "min_child_samples": 20,
            "subsample": 0.8,
            "reg_alpha": 0.1,
            "reg_lambda": 0.1,
            "random_state": 42,
            "n_jobs": -1,
            "verbose": -1,
        }

        # Pending observations: (price_at_t, features_at_t)
        self._pending: deque[tuple[float, dict]] = deque()
        # Labeled training set: (feature_vector, label)
        self._labeled_X: list[list[float]] = []
        self._labeled_y: list[int] = []
        self._feature_names: list[str] = []

        self._labeled_count: int = 0
        self._model = None
        self._is_trained: bool = False
        self._importances: dict = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(self, price: float, features: dict) -> None:
        """
        Register a new tick. Auto-labels pending observations after horizon_bars.
        Triggers async retraining when retrain_every labels are collected.
        """
        if not features or price <= 0:
            return

        # Add current observation to pending queue
        self._pending.append((price, features))

        # Label all observations that have matured (horizon_bars old)
        while len(self._pending) > self.horizon_bars:
            old_price, old_features = self._pending.popleft()
            future_return = (price - old_price) / old_price
            label = 1 if future_return > 0 else 0
            fvec = self._features_to_vector(old_features)
            if fvec is not None:
                self._labeled_X.append(fvec)
                self._labeled_y.append(label)
                self._labeled_count += 1

        # Cap training set size
        if len(self._labeled_X) > self.max_labeled:
            excess = len(self._labeled_X) - self.max_labeled
            self._labeled_X = self._labeled_X[excess:]
            self._labeled_y = self._labeled_y[excess:]

        # Retrain trigger
        if self._labeled_count > 0 and self._labeled_count % self.retrain_every == 0:
            threading.Thread(target=self._retrain, daemon=True).start()

    def predict(self, features: dict) -> Optional[dict]:
        """
        Predict direction and probability from current feature vector.
        Returns None if the model has not been trained yet.
        """
        if not self._is_trained or self._model is None:
            return None

        fvec = self._features_to_vector(features)
        if fvec is None:
            return None

        try:
            proba = self._model.predict_proba([fvec])[0]  # [P(DOWN), P(UP)]
            p_up = float(proba[1])
            direction = "UP" if p_up >= 0.5 else "DOWN"

            return {
                "direction": direction,
                "probability": round(p_up, 6),
                "feature_importances": self._importances,
                "labeled_count": self._labeled_count,
                "is_trained": True,
            }
        except Exception as e:
            logger.warning("LGBM predict error", error=str(e))
            return None

    @property
    def is_trained(self) -> bool:
        return self._is_trained

    @property
    def labeled_count(self) -> int:
        return self._labeled_count

    # ── Lifecycle: persist / restore ─────────────────────────────────────────

    def save_state(self) -> dict:
        """Return a picklable snapshot of the model state."""
        with self._lock:
            return {
                "model": self._model,
                "feature_names": list(self._feature_names),
                "labeled_count": self._labeled_count,
                "is_trained": self._is_trained,
                "importances": dict(self._importances),
                # Keep last 500 samples for drift detection after reload
                "recent_X": self._labeled_X[-500:],
                "recent_y": self._labeled_y[-500:],
            }

    def load_state(self, state: dict) -> None:
        """Restore model state from a dict produced by save_state()."""
        with self._lock:
            self._model = state.get("model")
            self._feature_names = list(state.get("feature_names", []))
            self._labeled_count = state.get("labeled_count", 0)
            self._is_trained = state.get("is_trained", False)
            self._importances = dict(state.get("importances", {}))
            self._labeled_X = list(state.get("recent_X", []))
            self._labeled_y = list(state.get("recent_y", []))

    def rolling_accuracy(self, n: int = 100) -> Optional[float]:
        """
        Accuracy of the current model on the last n labeled samples.
        Returns None if the model is not trained or there are fewer than n samples.
        Used for drift detection: a drop below ~0.48 suggests distribution shift.
        """
        if not self._is_trained or self._model is None or len(self._labeled_X) < n:
            return None
        try:
            X = np.array(self._labeled_X[-n:], dtype=np.float32)
            y = np.array(self._labeled_y[-n:], dtype=np.int32)
            preds = self._model.predict(X)
            return float(np.mean(preds == y))
        except Exception as e:
            logger.warning("rolling_accuracy failed", error=str(e))
            return None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _features_to_vector(self, features: dict) -> Optional[list[float]]:
        """Convert feature dict to a fixed-length numeric vector."""
        # On first call, establish the canonical feature order
        if not self._feature_names:
            self._feature_names = sorted(
                k for k, v in features.items()
                if not k.startswith("_") and isinstance(v, float) and np.isfinite(v)
            )

        if not self._feature_names:
            return None

        vec = []
        for name in self._feature_names:
            val = features.get(name, 0.0)
            if not isinstance(val, float) or not np.isfinite(val):
                val = 0.0
            vec.append(val)

        return vec

    def _retrain(self) -> None:
        """Retrain LightGBM model on the accumulated labeled set (runs in thread)."""
        try:
            from lightgbm import LGBMClassifier

            X = np.array(self._labeled_X, dtype=np.float32)
            y = np.array(self._labeled_y, dtype=np.int32)

            # Need at least 2 classes to train
            if len(np.unique(y)) < 2 or len(X) < 50:
                return

            model = LGBMClassifier(**self._lgbm_params)
            model.fit(X, y)

            # Feature importances (top 10 by gain)
            if hasattr(model, "feature_importances_") and self._feature_names:
                importances = dict(zip(self._feature_names, model.feature_importances_))
                top10 = dict(
                    sorted(importances.items(), key=lambda x: x[1], reverse=True)[:10]
                )
            else:
                top10 = {}

            with self._lock:
                self._model = model
                self._importances = top10
                self._is_trained = True

            logger.info(
                "LGBM retrained",
                n_samples=len(X),
                labeled_total=self._labeled_count,
                top_feature=next(iter(top10), "?"),
            )

        except Exception as e:
            logger.error("LGBM retrain failed", error=str(e))
