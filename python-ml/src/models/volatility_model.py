"""
Volatility predictor — GARCH(1,1) with HAR-RV fallback.

GARCH(1,1): fits a Generalized Autoregressive Conditional Heteroskedasticity
model on the return series. Best-in-class for financial volatility.

HAR-RV (Heterogeneous Autoregressive Realized Variance): uses a weighted
combination of short, medium, and long-horizon realized volatilities.
Simpler, more robust, excellent fallback.

Output per call:
  {
    "conditional_vol": float,        # current estimated vol (annualized)
    "vol_forecast_1h": float,        # 1-hour ahead forecast
    "vol_forecast_4h": float,        # 4-hour ahead forecast
    "vol_regime_prob": float,        # P(high-vol regime) [0, 1]
    "method": "garch" | "har_rv" | "realized",
  }
"""

from __future__ import annotations

import threading
import warnings
from collections import deque
from typing import Optional

import numpy as np
import structlog

logger = structlog.get_logger()

warnings.filterwarnings("ignore")

# Annualization factor (assuming 252 trading days × 6.5h × 3600s ≈ 6.5M ticks/year)
# For per-tick vol at 1Hz: sqrt(252 * 6.5 * 3600)
_ANNUALIZE_1HZ = np.sqrt(252 * 6.5 * 3600)
_ANNUALIZE_1D = np.sqrt(252)


class VolatilityPredictor:
    """
    Streaming volatility estimator with GARCH(1,1) + HAR-RV fallback.

    Maintains a rolling window of returns and periodically fits
    a GARCH model in a background thread.
    """

    def __init__(
        self,
        max_returns: int = 5_000,
        retrain_every: int = 500,
        min_obs: int = 100,
    ):
        self.max_returns = max_returns
        self.retrain_every = retrain_every
        self.min_obs = min_obs

        self._prices: deque[float] = deque(maxlen=max_returns + 1)
        self._returns: deque[float] = deque(maxlen=max_returns)
        self._obs_count: int = 0

        # GARCH fit results (updated in background thread)
        self._garch_params: Optional[dict] = None  # {omega, alpha, beta}
        self._garch_conditional_var: float = 0.0
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def observe(self, price: float) -> None:
        """Add a new price observation."""
        if price <= 0:
            return

        self._prices.append(price)

        if len(self._prices) >= 2:
            r = float(np.log(self._prices[-1] / self._prices[-2]))
            self._returns.append(r)
            self._obs_count += 1

            if self._obs_count % self.retrain_every == 0 and len(self._returns) >= self.min_obs:
                threading.Thread(target=self._fit_garch, daemon=True).start()

    def predict(self) -> dict:
        """
        Compute volatility estimates from current return history.
        Falls back gracefully when insufficient data or GARCH fails.
        """
        returns = list(self._returns)

        if len(returns) < 5:
            return {
                "conditional_vol": 0.0,
                "vol_forecast_1h": 0.0,
                "vol_forecast_4h": 0.0,
                "vol_regime_prob": 0.0,
                "method": "insufficient_data",
            }

        # Try GARCH first
        with self._lock:
            garch_params = self._garch_params
            garch_cv = self._garch_conditional_var

        if garch_params is not None and garch_cv > 0:
            return self._garch_predict(returns, garch_params, garch_cv)

        # Fall back to HAR-RV
        return self._har_rv_predict(returns)

    # ── Lifecycle: persist / restore ─────────────────────────────────────────

    def save_state(self) -> dict:
        """Return a picklable snapshot of the fitted GARCH parameters."""
        with self._lock:
            return {
                "garch_params": self._garch_params,
                "garch_conditional_var": self._garch_conditional_var,
            }

    def load_state(self, state: dict) -> None:
        """Restore GARCH parameters from a dict produced by save_state()."""
        with self._lock:
            self._garch_params = state.get("garch_params")
            self._garch_conditional_var = state.get("garch_conditional_var", 0.0)

    # ── Internal: HAR-RV ─────────────────────────────────────────────────────

    def _har_rv_predict(self, returns: list[float]) -> dict:
        """
        Heterogeneous AR Realized Variance model.
        rv_t = c + β_d × rv_{t-1d} + β_w × rv_{t-5d} + β_m × rv_{t-22d} + ε
        """
        arr = np.array(returns)

        # Realized volatilities at different horizons (in ticks at 1Hz)
        rv_1 = float(np.std(arr[-min(60, len(arr)):]))          # ~1min
        rv_5 = float(np.std(arr[-min(300, len(arr)):]))          # ~5min
        rv_22 = float(np.std(arr[-min(1320, len(arr)):]))        # ~22min

        # HAR-RV forecast (simplified single-step)
        conditional_vol_raw = 0.4 * rv_1 + 0.35 * rv_5 + 0.25 * rv_22
        conditional_vol = float(conditional_vol_raw * _ANNUALIZE_1HZ)

        # Vol regime: high if annualized vol > 40% (empirical threshold)
        vol_regime_prob = float(min(1.0, conditional_vol / 0.80))

        return {
            "conditional_vol": round(conditional_vol, 8),
            "vol_forecast_1h": round(conditional_vol * 0.9, 8),   # slight mean reversion
            "vol_forecast_4h": round(conditional_vol * 0.85, 8),
            "vol_regime_prob": round(vol_regime_prob, 6),
            "method": "har_rv",
        }

    # ── Internal: GARCH ──────────────────────────────────────────────────────

    def _garch_predict(self, returns: list[float], params: dict, cv: float) -> dict:
        """Compute forecast from fitted GARCH parameters."""
        omega = params["omega"]
        alpha = params["alpha"]
        beta = params["beta"]

        # GARCH(1,1) update: h_t = omega + alpha*r_{t-1}^2 + beta*h_{t-1}
        r_last = returns[-1] if returns else 0.0
        h_current = omega + alpha * r_last**2 + beta * cv

        # Multi-step forecast: E[h_{t+k}] = omega/(1-alpha-beta) + (alpha+beta)^k * (h_t - omega/(1-alpha-beta))
        persistence = alpha + beta
        if persistence < 1.0:
            long_run_var = omega / (1.0 - persistence)
        else:
            long_run_var = h_current

        def forecast_k(k: int) -> float:
            return long_run_var + (persistence ** k) * (h_current - long_run_var)

        # Convert variance to annualized vol
        cv_ann = float(np.sqrt(max(h_current, 1e-12)) * _ANNUALIZE_1HZ)
        h1_ann = float(np.sqrt(max(forecast_k(3600), 1e-12)) * _ANNUALIZE_1HZ)    # 1h = 3600 ticks
        h4_ann = float(np.sqrt(max(forecast_k(14400), 1e-12)) * _ANNUALIZE_1HZ)  # 4h = 14400 ticks

        vol_regime_prob = float(min(1.0, cv_ann / 0.80))

        with self._lock:
            self._garch_conditional_var = h_current

        return {
            "conditional_vol": round(cv_ann, 8),
            "vol_forecast_1h": round(h1_ann, 8),
            "vol_forecast_4h": round(h4_ann, 8),
            "vol_regime_prob": round(vol_regime_prob, 6),
            "method": "garch",
        }

    def _fit_garch(self) -> None:
        """Fit GARCH(1,1) on the current return history (background thread)."""
        try:
            from arch import arch_model

            returns_arr = np.array(list(self._returns)) * 100  # scale to % for numerical stability

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                am = arch_model(returns_arr, vol="GARCH", p=1, q=1, rescale=False)
                res = am.fit(disp="off", show_warning=False, options={"maxiter": 200})

            omega = float(res.params.get("omega", 1e-6))
            alpha = float(res.params.get("alpha[1]", 0.1))
            beta = float(res.params.get("beta[1]", 0.8))

            # Sanity check
            if not (0 <= alpha < 1 and 0 <= beta < 1 and alpha + beta < 1 and omega > 0):
                return

            # Get conditional variance from last fitted value
            cond_var = float(res.conditional_volatility.iloc[-1] ** 2) / 10000  # back to decimal

            with self._lock:
                self._garch_params = {"omega": omega / 10000, "alpha": alpha, "beta": beta}
                self._garch_conditional_var = cond_var

            logger.info(
                "GARCH fitted",
                alpha=round(alpha, 4),
                beta=round(beta, 4),
                persistence=round(alpha + beta, 4),
            )

        except Exception as e:
            logger.debug("GARCH fit failed, using HAR-RV fallback", error=str(e))
