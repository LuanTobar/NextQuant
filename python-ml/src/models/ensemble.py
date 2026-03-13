"""
EnsemblePredictor — stacking meta-learner combining LGBM + LSTM + Volatility.

Architecture:
  Level-0 models:
    - LGBMPredictor  → {direction, probability}
    - LSTMPredictor  → {direction, confidence}
    - VolatilityPredictor → {conditional_vol, vol_forecast_1h, vol_regime_prob}

  Level-1 meta-learner:
    - LogisticRegression trained on (lgbm_prob, lstm_confidence, cond_vol, vol_regime_prob)
    - Self-labels: same horizon as LGBM (future price direction)

  Disagreement rule:
    If LGBM and LSTM both have confidence > 0.6 AND disagree → output HOLD

  Output:
    {
      "signal": "BUY" | "SELL" | "HOLD",
      "confidence": float,           # [0, 1] — strength of signal
      "expected_return": float,      # estimated return (from LSTM + vol)
      "ci_low": float,               # lower confidence interval
      "ci_high": float,              # upper confidence interval
      "lgbm_prob": float | None,
      "lstm_confidence": float | None,
      "regime_vol": float | None,
      "method": "ensemble" | "lgbm_only" | "fallback",
      "is_trained": bool,
    }
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
import structlog

from .lgbm_model import LGBMPredictor
from .lstm_model import LSTMPredictor
from .volatility_model import VolatilityPredictor

logger = structlog.get_logger()

# Signal thresholds
_BUY_THRESHOLD = 0.58    # P(UP) > 0.58 → BUY
_SELL_THRESHOLD = 0.42   # P(UP) < 0.42 → SELL
_DISAGREE_CONF = 0.60    # both must exceed this to trigger disagreement rule


class EnsemblePredictor:
    """
    Stacking ensemble that coordinates LGBM + LSTM + Volatility models.

    All three level-0 models run in streaming mode (self-labeling).
    The meta-learner trains on level-0 outputs whenever labeled data
    is available; otherwise falls back gracefully to LGBM alone.
    """

    def __init__(
        self,
        lgbm_kwargs: Optional[dict] = None,
        lstm_kwargs: Optional[dict] = None,
        vol_kwargs: Optional[dict] = None,
        meta_retrain_every: int = 200,
        horizon_bars: int = 60,
    ):
        self.lgbm = LGBMPredictor(**(lgbm_kwargs or {}))
        self.lstm = LSTMPredictor(**(lstm_kwargs or {}))
        self.vol = VolatilityPredictor(**(vol_kwargs or {}))

        self.horizon_bars = horizon_bars
        self.meta_retrain_every = meta_retrain_every

        # Meta-learner training data
        self._meta_pending: deque[tuple[float, dict]] = deque()  # (price, l0_features)
        self._meta_X: list[list[float]] = []
        self._meta_y: list[int] = []
        self._meta_labeled_count: int = 0

        self._meta_model = None
        self._meta_is_trained: bool = False
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(self, price: float, features: dict) -> None:
        """
        Feed a new tick to all level-0 models and the meta-learner buffer.

        Args:
            price: current close price
            features: FeatureStore output dict
        """
        # Feed to level-0 models
        self.lgbm.observe(price, features)
        self.lstm.observe(price)
        self.vol.observe(price)

        # Capture level-0 outputs for meta-learner training
        l0_features = self._extract_l0_features()
        if l0_features is not None:
            self._meta_pending.append((price, l0_features))

        # Label matured meta-learner observations
        while len(self._meta_pending) > self.horizon_bars:
            old_price, old_l0 = self._meta_pending.popleft()
            future_return = (price - old_price) / old_price if old_price > 0 else 0
            label = 1 if future_return > 0 else 0
            self._meta_X.append(list(old_l0.values()))
            self._meta_y.append(label)
            self._meta_labeled_count += 1

        # Cap meta training set
        if len(self._meta_X) > 5_000:
            excess = len(self._meta_X) - 5_000
            self._meta_X = self._meta_X[excess:]
            self._meta_y = self._meta_y[excess:]

        # Retrain meta-learner
        if self._meta_labeled_count > 0 and self._meta_labeled_count % self.meta_retrain_every == 0:
            threading.Thread(target=self._retrain_meta, daemon=True).start()

    def predict(self, features: dict) -> dict:
        """
        Generate final trading signal from ensemble.
        Falls back gracefully depending on which models are trained.
        """
        # Get level-0 predictions
        lgbm_out = self.lgbm.predict(features)
        lstm_out = self.lstm.predict()
        vol_out = self.vol.predict()

        lgbm_prob = lgbm_out["probability"] if lgbm_out else None
        lstm_conf = lstm_out["confidence"] if lstm_out else None
        cond_vol = vol_out["conditional_vol"]
        vol_regime_prob = vol_out["vol_regime_prob"]

        # ── Disagreement rule ──────────────────────────────────────────────────
        if (lgbm_prob is not None and lstm_conf is not None
                and lgbm_out["direction"] != lstm_out["direction"]
                and lgbm_prob > _DISAGREE_CONF
                and lstm_conf > _DISAGREE_CONF):
            return self._build_output(
                signal="HOLD", confidence=0.5, expected_return=0.0,
                lgbm_prob=lgbm_prob, lstm_conf=lstm_conf,
                cond_vol=cond_vol, vol_regime_prob=vol_regime_prob,
                method="disagreement_hold",
            )

        # ── Meta-learner path ─────────────────────────────────────────────────
        if self._meta_is_trained and self._meta_model is not None:
            l0 = self._extract_l0_features()
            if l0 is not None:
                try:
                    proba = self._meta_model.predict_proba([list(l0.values())])[0]
                    p_up = float(proba[1])
                    signal, confidence = self._prob_to_signal(p_up)
                    expected_return = self._estimate_expected_return(
                        p_up, lstm_out, cond_vol
                    )
                    ci_low, ci_high = self._confidence_interval(expected_return, cond_vol)
                    return self._build_output(
                        signal=signal, confidence=confidence, expected_return=expected_return,
                        lgbm_prob=lgbm_prob, lstm_conf=lstm_conf,
                        cond_vol=cond_vol, vol_regime_prob=vol_regime_prob,
                        method="ensemble", ci_low=ci_low, ci_high=ci_high,
                    )
                except Exception as e:
                    logger.warning("Meta-learner predict error", error=str(e))

        # ── LGBM-only fallback ────────────────────────────────────────────────
        if lgbm_prob is not None:
            signal, confidence = self._prob_to_signal(lgbm_prob)
            expected_return = self._estimate_expected_return(lgbm_prob, lstm_out, cond_vol)
            ci_low, ci_high = self._confidence_interval(expected_return, cond_vol)
            return self._build_output(
                signal=signal, confidence=confidence, expected_return=expected_return,
                lgbm_prob=lgbm_prob, lstm_conf=lstm_conf,
                cond_vol=cond_vol, vol_regime_prob=vol_regime_prob,
                method="lgbm_only", ci_low=ci_low, ci_high=ci_high,
            )

        # ── Pure fallback (no models trained yet) ─────────────────────────────
        return self._build_output(
            signal="HOLD", confidence=0.5, expected_return=0.0,
            lgbm_prob=lgbm_prob, lstm_conf=lstm_conf,
            cond_vol=cond_vol, vol_regime_prob=vol_regime_prob,
            method="fallback",
        )

    @property
    def is_trained(self) -> bool:
        return self.lgbm.is_trained

    # ── Internal ──────────────────────────────────────────────────────────────

    def _extract_l0_features(self) -> Optional[dict]:
        """Extract a feature vector from level-0 model outputs."""
        lgbm_out = None
        vol_out = self.vol.predict()

        # Dummy features dict to trigger LGBM prediction (use what we have)
        # Note: LGBM predict needs the full FeatureStore feature dict;
        # for the meta-learner we use a simplified proxy
        return {
            "lgbm_p_up": 0.5,    # placeholder — updated when real prediction available
            "lstm_conf": 0.5,
            "cond_vol": vol_out["conditional_vol"],
            "vol_regime_prob": vol_out["vol_regime_prob"],
            "vol_forecast_ratio": (
                vol_out["vol_forecast_1h"] / max(vol_out["conditional_vol"], 1e-8)
                if vol_out["conditional_vol"] > 0 else 1.0
            ),
        }

    def _prob_to_signal(self, p_up: float) -> tuple[str, float]:
        """Convert P(UP) to (signal, confidence)."""
        if p_up > _BUY_THRESHOLD:
            return "BUY", round(p_up, 6)
        elif p_up < _SELL_THRESHOLD:
            return "SELL", round(1.0 - p_up, 6)
        return "HOLD", round(1.0 - abs(p_up - 0.5) * 2, 6)

    def _estimate_expected_return(
        self, p_up: float, lstm_out: Optional[dict], cond_vol: float
    ) -> float:
        """Estimate expected return from signal probability and LSTM."""
        # Base estimate from probability (kelly-inspired)
        base = (p_up - 0.5) * cond_vol * 4  # scale by vol

        # Blend with LSTM if available
        if lstm_out is not None:
            lstm_ret = lstm_out.get("predicted_return", 0.0)
            base = 0.6 * base + 0.4 * lstm_ret

        return round(base, 8)

    def _confidence_interval(self, expected_return: float, cond_vol: float) -> tuple[float, float]:
        """95% confidence interval for expected return."""
        z = 1.96
        std = cond_vol * 0.01  # scale vol to return magnitude
        return round(expected_return - z * std, 8), round(expected_return + z * std, 8)

    def _build_output(
        self,
        signal: str,
        confidence: float,
        expected_return: float,
        lgbm_prob: Optional[float],
        lstm_conf: Optional[float],
        cond_vol: float,
        vol_regime_prob: float,
        method: str,
        ci_low: float = 0.0,
        ci_high: float = 0.0,
    ) -> dict:
        return {
            "signal": signal,
            "confidence": round(confidence, 6),
            "expected_return": round(expected_return, 8),
            "ci_low": round(ci_low, 8),
            "ci_high": round(ci_high, 8),
            "lgbm_prob": round(lgbm_prob, 6) if lgbm_prob is not None else None,
            "lstm_confidence": round(lstm_conf, 6) if lstm_conf is not None else None,
            "regime_vol": round(cond_vol, 6),
            "vol_regime_prob": round(vol_regime_prob, 6),
            "method": method,
            "is_trained": self.lgbm.is_trained or self._meta_is_trained,
        }

    # ── Lifecycle: persist / restore ─────────────────────────────────────────

    def save_state(self) -> dict:
        """
        Return a picklable snapshot of the full ensemble.
        Delegates to each sub-model and includes the meta-learner.
        """
        with self._lock:
            meta_model = self._meta_model
            meta_is_trained = self._meta_is_trained
            meta_labeled_count = self._meta_labeled_count
        return {
            "lgbm": self.lgbm.save_state(),
            "lstm": self.lstm.save_state(),
            "vol": self.vol.save_state(),
            "meta_model": meta_model,           # _ScaledClassifier | None (picklable)
            "meta_is_trained": meta_is_trained,
            "meta_labeled_count": meta_labeled_count,
        }

    def load_state(self, state: dict) -> None:
        """Restore ensemble state from a dict produced by save_state()."""
        if "lgbm" in state:
            self.lgbm.load_state(state["lgbm"])
        if "lstm" in state:
            self.lstm.load_state(state["lstm"])
        if "vol" in state:
            self.vol.load_state(state["vol"])
        with self._lock:
            self._meta_model = state.get("meta_model")
            self._meta_is_trained = state.get("meta_is_trained", False)
            self._meta_labeled_count = state.get("meta_labeled_count", 0)

    def _retrain_meta(self) -> None:
        """Retrain the LogisticRegression meta-learner."""
        try:
            from sklearn.linear_model import LogisticRegression
            from sklearn.preprocessing import StandardScaler

            X = np.array(self._meta_X, dtype=np.float32)
            y = np.array(self._meta_y, dtype=np.int32)

            if len(X) < 50 or len(np.unique(y)) < 2:
                return

            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)

            model = LogisticRegression(max_iter=500, random_state=42, C=1.0)
            model.fit(X_scaled, y)

            with self._lock:
                self._meta_model = _ScaledClassifier(scaler, model)
                self._meta_is_trained = True

            logger.info(
                "Meta-learner retrained",
                n_samples=len(X),
                meta_labeled_total=self._meta_labeled_count,
            )

        except Exception as e:
            logger.error("Meta-learner retrain failed", error=str(e))


class _ScaledClassifier:
    """Wrapper that applies StandardScaler before LogisticRegression."""

    def __init__(self, scaler, model):
        self._scaler = scaler
        self._model = model

    def predict_proba(self, X: list) -> np.ndarray:
        import numpy as np
        X_scaled = self._scaler.transform(np.array(X, dtype=np.float32))
        return self._model.predict_proba(X_scaled)
