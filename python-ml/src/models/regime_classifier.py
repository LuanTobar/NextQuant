"""
HMMRegimeClassifier — 5-state Gaussian HMM for market regime detection.

5 regimes:
  BULL_QUIET:    low vol, positive drift
  BULL_VOLATILE: high vol, positive drift
  SIDEWAYS:      medium vol, flat drift
  BEAR_QUIET:    low vol, negative drift
  BEAR_VOLATILE: high vol, negative drift

Feature vector fed to HMM per tick:
  [log_return, rolling_vol_5, rolling_vol_20, vol_ratio_short_long]

Falls back to volatility-threshold classifier (backward-compat output)
if HMM not yet fitted.

Output of classify():
  {
    "regime": str,                  # one of the 5 regime names
    "probabilities": dict[str, float],  # posterior for each regime
    "state_idx": int,               # raw HMM state index (-1 = fallback)
    "volatility": float,            # annualized vol (1Hz ticks)
    "method": "hmm_5state" | "volatility_threshold",
  }
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()

# Canonical 5-regime names
_REGIME_NAMES = [
    "BULL_QUIET",
    "BULL_VOLATILE",
    "SIDEWAYS",
    "BEAR_QUIET",
    "BEAR_VOLATILE",
]

# Annualization factor for 1Hz tick data
_ANNUALIZE = np.sqrt(252 * 6.5 * 3600)


class RegimeClassifier:
    """
    5-state Gaussian HMM regime classifier with volatility-threshold fallback.

    Maintains a rolling return buffer per symbol. Periodically fits a
    GaussianHMM in a background thread. classify() decodes the current state
    via Viterbi and returns posterior probabilities for all 5 regimes.

    Backward-compatible with the legacy 3-state API:
      add_tick(symbol, close)
      classify(symbol) → {regime, probabilities, volatility, method}
    """

    def __init__(
        self,
        window: int = 20,          # minimum bars for fallback vol calc
        n_states: int = 5,
        max_returns: int = 2_000,
        retrain_every: int = 500,
        min_obs: int = 200,
    ):
        self.window = window
        self.n_states = n_states
        self.max_returns = max_returns
        self.retrain_every = retrain_every
        self.min_obs = min_obs

        # Per-symbol buffers
        self._prices: dict[str, deque] = {}
        self._returns: dict[str, deque] = {}
        self._obs_count: dict[str, int] = {}

        # Fitted artifacts (thread-safe via lock)
        self._models: dict[str, object] = {}
        self._state_maps: dict[str, dict[int, str]] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def add_tick(self, symbol: str, close: float) -> None:
        """Buffer a price tick; triggers async HMM refit when ready."""
        if close <= 0:
            return

        if symbol not in self._prices:
            self._prices[symbol] = deque(maxlen=self.max_returns + 1)
            self._returns[symbol] = deque(maxlen=self.max_returns)
            self._obs_count[symbol] = 0

        self._prices[symbol].append(close)

        if len(self._prices[symbol]) >= 2:
            r = float(np.log(self._prices[symbol][-1] / self._prices[symbol][-2]))
            self._returns[symbol].append(r)
            self._obs_count[symbol] += 1

            count = self._obs_count[symbol]
            if count % self.retrain_every == 0 and count >= self.min_obs:
                returns_snapshot = list(self._returns[symbol])
                threading.Thread(
                    target=self._fit_hmm,
                    args=(symbol, returns_snapshot),
                    daemon=True,
                ).start()

    def classify(self, symbol: str) -> dict:
        """Classify the current regime for the given symbol."""
        returns = list(self._returns.get(symbol, []))

        if len(returns) < self.window:
            return self._fallback(0.0)

        # Current volatility (always computed for enrichment)
        recent_r = np.array(returns[-self.window:])
        annualized_vol = float(np.std(recent_r) * _ANNUALIZE)

        with self._lock:
            model = self._models.get(symbol)
            state_map = self._state_maps.get(symbol)

        if model is None or state_map is None:
            return self._fallback(annualized_vol)

        try:
            return self._hmm_classify(returns, model, state_map, annualized_vol)
        except Exception as e:
            logger.debug("HMM classify error, using fallback", symbol=symbol, error=str(e))
            return self._fallback(annualized_vol)

    # ── Lifecycle: persist / restore ─────────────────────────────────────────

    def save_state(self) -> dict:
        """
        Return a picklable snapshot.
        GaussianHMM from hmmlearn implements pickle protocol — safe for joblib.
        """
        with self._lock:
            return {
                "models": dict(self._models),
                "state_maps": dict(self._state_maps),
                "obs_counts": dict(self._obs_count),
            }

    def load_state(self, state: dict) -> None:
        """Restore HMM models and metadata from a dict produced by save_state().
        Models that contain NaN parameters are discarded so they are retrained
        cleanly rather than causing downstream startprob_ errors.
        """
        raw_models = dict(state.get("models", {}))
        state_maps = dict(state.get("state_maps", {}))
        obs_counts = dict(state.get("obs_counts", {}))

        valid_models: dict = {}
        valid_maps: dict = {}
        valid_counts: dict = {}
        for symbol, model in raw_models.items():
            try:
                sp = getattr(model, "startprob_", None)
                if sp is None or np.any(np.isnan(sp)) or not np.isfinite(sp).all():
                    logger.warning("Discarding HMM with NaN startprob_ on load", symbol=symbol)
                    continue
                means = getattr(model, "means_", None)
                if means is None or not np.isfinite(means).all():
                    logger.warning("Discarding HMM with NaN means_ on load", symbol=symbol)
                    continue
                valid_models[symbol] = model
                valid_maps[symbol] = state_maps.get(symbol, {})
                valid_counts[symbol] = obs_counts.get(symbol, 0)
            except Exception as exc:
                logger.warning("Discarding corrupt HMM on load", symbol=symbol, error=str(exc))

        # Restore obs_counts for symbols not yet trained (no model in state)
        for symbol, count in obs_counts.items():
            if symbol not in valid_counts:
                valid_counts[symbol] = count

        with self._lock:
            self._models = valid_models
            self._state_maps = valid_maps
            self._obs_count = valid_counts

    # ── Internal: HMM fitting ─────────────────────────────────────────────────

    def _build_features(self, returns: list[float]) -> np.ndarray:
        """Build (N, 4) feature matrix: [ret, vol_5, vol_20, vol_ratio]."""
        arr = np.array(returns, dtype=np.float64)
        n = len(arr)

        vol_5 = np.array([
            np.std(arr[max(0, i - 4):i + 1]) for i in range(n)
        ])
        vol_20 = np.array([
            np.std(arr[max(0, i - 19):i + 1]) for i in range(n)
        ])
        # Short/long vol ratio — momentum of volatility
        vol_ratio = np.where(vol_20 > 1e-12, vol_5 / vol_20, 1.0)

        X = np.column_stack([arr, vol_5, vol_20, vol_ratio])
        return np.nan_to_num(X, nan=0.0, posinf=1.0, neginf=-1.0)

    def _fit_hmm(self, symbol: str, returns: list[float]) -> None:
        """Fit GaussianHMM(5) in a background daemon thread."""
        try:
            from hmmlearn.hmm import GaussianHMM

            X = self._build_features(returns)
            model = GaussianHMM(
                n_components=self.n_states,
                covariance_type="diag",
                n_iter=100,
                random_state=42,
                verbose=False,
            )
            model.fit(X)

            state_map = self._name_states(model.means_)

            with self._lock:
                self._models[symbol] = model
                self._state_maps[symbol] = state_map

            logger.info(
                "HMM 5-state fitted",
                symbol=symbol,
                n_obs=len(returns),
                regime_map={str(k): v for k, v in state_map.items()},
            )

        except ImportError:
            logger.warning("hmmlearn not installed — HMM unavailable, using vol-threshold fallback")
        except Exception as e:
            logger.debug("HMM fit failed", symbol=symbol, error=str(e))

    def _name_states(self, means: np.ndarray) -> dict[int, str]:
        """
        Assign regime names to HMM states by sorting on (mean_return, mean_vol).

        mean_return = means[:, 0] (log return feature)
        mean_vol    = means[:, 2] (rolling_vol_20 feature)

        Sort order: bottom 2 = BEAR group, middle = SIDEWAYS, top 2 = BULL.
        Within each group: lower vol → QUIET, higher vol → VOLATILE.
        """
        n = self.n_states
        ret_order = np.argsort(means[:, 0])   # indices sorted by mean return

        state_map: dict[int, str] = {}

        if n == 5:
            # Positions in sorted order
            b0, b1 = ret_order[0], ret_order[1]   # BEAR group (lowest returns)
            sw    = ret_order[2]                    # SIDEWAYS (middle)
            u0, u1 = ret_order[3], ret_order[4]   # BULL group (highest returns)

            # Within BEAR: sort by vol (col 2) → lower = QUIET
            if means[b0, 2] <= means[b1, 2]:
                state_map[b0], state_map[b1] = "BEAR_QUIET", "BEAR_VOLATILE"
            else:
                state_map[b0], state_map[b1] = "BEAR_VOLATILE", "BEAR_QUIET"

            state_map[sw] = "SIDEWAYS"

            # Within BULL: sort by vol → lower = QUIET
            if means[u0, 2] <= means[u1, 2]:
                state_map[u0], state_map[u1] = "BULL_QUIET", "BULL_VOLATILE"
            else:
                state_map[u0], state_map[u1] = "BULL_VOLATILE", "BULL_QUIET"
        else:
            # Generic fallback for different n_states
            ordered_names = ["BEAR_VOLATILE", "BEAR_QUIET", "SIDEWAYS", "BULL_QUIET", "BULL_VOLATILE"]
            for rank, idx in enumerate(ret_order):
                state_map[idx] = ordered_names[min(rank, len(ordered_names) - 1)]

        return state_map

    def _hmm_classify(
        self,
        returns: list[float],
        model,
        state_map: dict[int, str],
        annualized_vol: float,
    ) -> dict:
        """Viterbi decode + posterior probabilities for all 5 regimes."""
        X = self._build_features(returns)

        # Viterbi: most likely state sequence
        state_seq = model.predict(X)
        current_state = int(state_seq[-1])
        regime = state_map.get(current_state, "SIDEWAYS")

        # Forward-backward: posterior probabilities per state
        try:
            posteriors = model.predict_proba(X)
            post = posteriors[-1]  # shape (n_states,)
        except Exception:
            post = np.ones(self.n_states) / self.n_states

        # Aggregate to regime names (handles n_states < 5 gracefully)
        probs: dict[str, float] = {name: 0.0 for name in _REGIME_NAMES}
        for state_idx, name in state_map.items():
            if 0 <= state_idx < len(post):
                probs[name] = probs.get(name, 0.0) + float(post[state_idx])

        # Normalize to sum=1
        total = sum(probs.values())
        if total > 1e-10:
            probs = {k: round(v / total, 4) for k, v in probs.items()}

        return {
            "regime": regime,
            "probabilities": probs,
            "state_idx": current_state,
            "volatility": round(annualized_vol, 6),
            "method": "hmm_5state",
        }

    # ── Fallback: volatility-threshold ───────────────────────────────────────

    def _fallback(self, volatility: float) -> dict:
        """
        Legacy 3-zone volatility classifier mapped to 5-regime output.
        Backward-compatible regime names used by downstream _generate_signal.
        """
        if volatility <= 0.0:
            regime = "SIDEWAYS"
            probs = {name: 0.2 for name in _REGIME_NAMES}
        elif volatility < 0.15:
            regime = "BULL_QUIET"
            probs = {
                "BULL_QUIET": 0.55, "BULL_VOLATILE": 0.10,
                "SIDEWAYS": 0.20, "BEAR_QUIET": 0.10, "BEAR_VOLATILE": 0.05,
            }
        elif volatility < 0.30:
            regime = "SIDEWAYS"
            probs = {
                "BULL_QUIET": 0.15, "BULL_VOLATILE": 0.15,
                "SIDEWAYS": 0.40, "BEAR_QUIET": 0.15, "BEAR_VOLATILE": 0.15,
            }
        else:
            regime = "BEAR_VOLATILE"
            probs = {
                "BULL_QUIET": 0.05, "BULL_VOLATILE": 0.10,
                "SIDEWAYS": 0.10, "BEAR_QUIET": 0.10, "BEAR_VOLATILE": 0.65,
            }

        return {
            "regime": regime,
            "probabilities": probs,
            "state_idx": -1,
            "volatility": round(volatility, 6),
            "method": "volatility_threshold",
        }
