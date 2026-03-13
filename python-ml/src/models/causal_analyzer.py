"""
CausalAnalyzer — backward-compatible wrapper over CausalEngine.

Sprint 1.3: Replaces DoWhy + correlation fallback with the Granger + TE
causal pipeline from src/causal/causal_engine.py.

Legacy API (unchanged):
  add_tick(tick: dict) → None
  analyze(symbol: str) → {causal_effect, method, description}

Extended output (Sprint 1.3+):
  analyze() also returns:
    "relationships": list[dict]   — directed causal links
    "n_significant": int          — number of significant links
    "alpha_signal":  float        — directional alpha [-1, +1]
"""

from __future__ import annotations

import structlog

from src.causal.causal_engine import CausalEngine

logger = structlog.get_logger()


class CausalAnalyzer:
    """
    Streaming causal analyzer for market tick data.

    Delegates to CausalEngine (Granger + Transfer Entropy) and exposes
    the legacy add_tick / analyze interface used by MLService.
    """

    def __init__(
        self,
        lookback: int = 100,
        analyze_every: int = 50,
    ):
        self._engine = CausalEngine(
            lookback=lookback,
            analyze_every=analyze_every,
            max_granger_lag=5,
            te_k=1,
            granger_alpha=0.05,
            te_threshold=0.005,
        )

    def add_tick(self, tick: dict) -> None:
        """Feed a raw market tick to the causal engine."""
        self._engine.add_tick(tick)

    def analyze(self, symbol: str, exchange: str = "US") -> dict:
        """
        Return latest causal analysis result.

        Always returns a dict with at least:
          causal_effect, method, description
        Plus extended fields when analysis is available:
          relationships, n_significant, alpha_signal
        """
        result = self._engine.analyze(symbol, exchange)

        # Ensure legacy fields are always present
        if "causal_effect" not in result:
            result["causal_effect"] = 0.0
        if "method" not in result:
            result["method"] = "insufficient_data"
        if "description" not in result:
            result["description"] = "No causal analysis available"

        return result
