"""
CausalEngine — Causal Alpha Pipeline orchestrator.

Runs two causal discovery methods on the streaming return/feature data:
  1. Granger Causality Filter   (statsmodels, frequentist F-test)
  2. Transfer Entropy estimator (custom binning-based, information-theoretic)

Synthesises all significant relationships into:
  - A causal graph (list of directed edges with strength)
  - An alpha_signal [-1, +1] derived from significant leading indicators

Design:
  - Operates on a rolling window of per-symbol and cross-asset returns
  - Runs in a background thread every `analyze_every` ticks to avoid blocking
  - Thread-safe: reads committed results under a lock

Output of analyze():
  {
    "relationships": list[dict],  # directed causal links
    "n_significant": int,
    "alpha_signal":  float,       # directional alpha from causal graph
    "causal_effect": float,       # alias for alpha_signal (legacy compat)
    "method":        str,
    "description":   str,
  }
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np
import structlog

from .granger_filter import granger_batch
from .transfer_entropy import transfer_entropy_batch

logger = structlog.get_logger()

# Variables to test as potential Granger causes of future returns
_CAUSAL_CANDIDATES = [
    "volume_change",
    "return_lag1",
    "return_lag2",
    "hl_range",          # high-low range proxy for intraday vol
]


class CausalEngine:
    """
    Streaming causal alpha pipeline.

    Feed ticks via add_tick(). The engine accumulates per-symbol return
    and volume series and runs Granger + TE tests in a background thread.
    analyze() returns the most recent causal graph immediately.
    """

    def __init__(
        self,
        lookback: int = 100,          # rolling window for causal tests
        analyze_every: int = 50,      # ticks between background re-analysis
        max_granger_lag: int = 5,
        te_k: int = 1,
        granger_alpha: float = 0.05,
        te_threshold: float = 0.005,
    ):
        self.lookback = lookback
        self.analyze_every = analyze_every
        self.max_granger_lag = max_granger_lag
        self.te_k = te_k
        self.granger_alpha = granger_alpha
        self.te_threshold = te_threshold

        # Per-symbol raw tick history
        self._ticks: dict[str, deque] = {}
        self._tick_count: dict[str, int] = {}

        # Latest committed results (updated by background thread)
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def add_tick(self, tick: dict) -> None:
        """
        Buffer a raw tick. Triggers background causal analysis every
        analyze_every ticks per symbol.
        """
        symbol = tick.get("symbol", "UNKNOWN")
        exchange = tick.get("exchange", "US")
        key = f"{exchange}:{symbol}"

        if key not in self._ticks:
            self._ticks[key] = deque(maxlen=self.lookback + 50)
            self._tick_count[key] = 0

        self._ticks[key].append(tick)
        self._tick_count[key] += 1

        count = self._tick_count[key]
        if count % self.analyze_every == 0 and len(self._ticks[key]) >= self.lookback:
            ticks_snapshot = list(self._ticks[key])
            threading.Thread(
                target=self._run_analysis,
                args=(key, ticks_snapshot),
                daemon=True,
            ).start()

    def analyze(self, symbol: str, exchange: str = "US") -> dict:
        """
        Return the latest causal analysis result for the symbol.
        Non-blocking: returns the last committed result or a fallback.
        """
        key = f"{exchange}:{symbol}"
        with self._lock:
            result = self._results.get(key)

        if result is not None:
            return result

        # Insufficient data fallback
        return {
            "relationships": [],
            "n_significant": 0,
            "alpha_signal": 0.0,
            "causal_effect": 0.0,
            "method": "insufficient_data",
            "description": "Not enough data for causal analysis",
        }

    # ── Internal: Analysis ────────────────────────────────────────────────────

    def _run_analysis(self, key: str, ticks: list[dict]) -> None:
        """
        Background analysis: build feature series, run Granger + TE, commit.
        """
        try:
            series = self._build_series(ticks)
            if series is None or len(next(iter(series.values()), [])) < 15:
                return

            target = "next_return"
            if target not in series:
                return

            # Granger causality
            granger_rels = granger_batch(
                series, target,
                max_lag=self.max_granger_lag,
                significance=self.granger_alpha,
            )

            # Transfer entropy
            te_rels = transfer_entropy_batch(
                series, target,
                k=self.te_k,
                threshold=self.te_threshold,
            )

            all_rels = granger_rels + te_rels
            n_sig = len(all_rels)

            # Alpha signal: weighted sum of signed causal strengths
            alpha_signal = self._compute_alpha(all_rels, series)

            description = (
                f"{n_sig} causal links found "
                f"(Granger: {len(granger_rels)}, TE: {len(te_rels)}); "
                f"alpha={alpha_signal:+.3f}"
            )

            result = {
                "relationships": all_rels,
                "n_significant": n_sig,
                "alpha_signal": round(alpha_signal, 4),
                "causal_effect": round(alpha_signal, 4),   # legacy compat
                "method": "granger_te",
                "description": description,
            }

            with self._lock:
                self._results[key] = result

            logger.info(
                "Causal analysis complete",
                symbol=key,
                n_significant=n_sig,
                alpha_signal=round(alpha_signal, 4),
            )

        except Exception as e:
            logger.debug("Causal analysis failed", symbol=key, error=str(e))

    def _build_series(self, ticks: list[dict]) -> Optional[dict[str, np.ndarray]]:
        """
        Extract causal feature series from raw ticks.

        Returns dict of {name: array} all aligned to the same length.
        """
        try:
            closes  = np.array([float(t.get("close",  0)) for t in ticks])
            volumes = np.array([float(t.get("volume", 0)) for t in ticks])
            highs   = np.array([float(t.get("high",   0)) for t in ticks])
            lows    = np.array([float(t.get("low",    0)) for t in ticks])

            if np.any(closes <= 0) or len(closes) < 15:
                return None

            # Log returns
            log_ret = np.diff(np.log(closes + 1e-12))
            # Volume changes (log)
            vol_chg = np.diff(np.log(volumes + 1))
            # High-low range / close (intraday volatility proxy)
            hl_range = (highs[1:] - lows[1:]) / (closes[1:] + 1e-12)
            # 1-lag and 2-lag return
            ret_lag1 = np.concatenate([[0.0], log_ret[:-1]])
            ret_lag2 = np.concatenate([[0.0, 0.0], log_ret[:-2]])
            # Target: next return (shift ret by -1)
            next_ret = np.concatenate([log_ret[1:], [0.0]])

            n = len(log_ret)
            return {
                "return":        log_ret[:n],
                "volume_change": vol_chg[:n],
                "hl_range":      hl_range[:n],
                "return_lag1":   ret_lag1[:n],
                "return_lag2":   ret_lag2[:n],
                "next_return":   next_ret[:n],
            }
        except Exception:
            return None

    def _compute_alpha(self, relationships: list[dict], series: dict) -> float:
        """
        Compute a directional alpha signal from the causal graph.

        For each significant relationship, the strength (positive/negative)
        indicates whether the causing variable predicts up or down movement.
        Alpha is the weighted average of strengths, clipped to [-1, 1].
        """
        if not relationships:
            return 0.0

        weighted_sum = 0.0
        total_weight = 0.0

        for rel in relationships:
            strength = rel.get("strength", 0.0)
            if strength is None:
                strength = 0.0

            # Weight by significance: lower p-value = higher weight
            p = rel.get("p_value") or 0.05
            weight = 1.0 - float(p) if p is not None else 0.5
            weight = max(0.0, min(1.0, weight))

            weighted_sum += float(strength) * weight
            total_weight += weight

        if total_weight < 1e-8:
            return 0.0

        alpha = weighted_sum / total_weight
        return float(np.clip(alpha, -1.0, 1.0))
