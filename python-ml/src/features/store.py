"""
FeatureStore — central orchestrator for all feature computation.

Responsibilities:
  - Maintains a rolling OHLCV tick buffer per (exchange, symbol)
  - Orchestrates all feature modules (technical, microstructure, cross_asset, momentum)
  - Caches computed features per symbol with configurable TTL
  - Persists feature snapshots to QuestDB (async, best-effort)
  - Thread-safe via asyncio (single-threaded event loop assumed)

Usage:
    store = FeatureStore()
    store.add_tick(tick_dict)
    features = store.compute_features("US", "AAPL")
    # features: dict with 80+ named float values
"""

from __future__ import annotations

import time
from collections import deque
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from .technical import compute_technical_features
from .microstructure import compute_microstructure_features
from .cross_asset import compute_cross_asset_features
from .momentum import compute_momentum_features

logger = structlog.get_logger()

# Maximum ticks per symbol in memory (≈83 min at 1Hz)
_BUFFER_MAXLEN = 5_000


class FeatureStore:
    """
    Central feature store for the Research Analyst agent.

    Thread-safety: designed for single-threaded asyncio use.
    All public methods are synchronous and safe to call from async context
    without blocking (pure CPU, no I/O).
    """

    def __init__(self, cache_ttl_s: float = 5.0):
        self._buffers: dict[str, deque[dict]] = {}
        # Cache: key → (computed_at_ts, features_dict)
        self._cache: dict[str, tuple[float, dict]] = {}
        self._cache_ttl = cache_ttl_s
        self._tick_counts: dict[str, int] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def add_tick(self, tick: dict) -> None:
        """
        Add a raw tick from the Rust Market Sentinel.

        Expected fields: symbol, exchange, open, high, low, close, volume, timestamp
        """
        exchange = tick.get("exchange", "US")
        symbol = tick.get("symbol", "")
        if not symbol:
            return

        key = f"{exchange}:{symbol}"

        if key not in self._buffers:
            self._buffers[key] = deque(maxlen=_BUFFER_MAXLEN)
            self._tick_counts[key] = 0

        self._buffers[key].append({
            "timestamp": tick.get("timestamp"),
            "open": float(tick.get("open", tick.get("close", 0.0))),
            "high": float(tick.get("high", tick.get("close", 0.0))),
            "low": float(tick.get("low", tick.get("close", 0.0))),
            "close": float(tick.get("close", 0.0)),
            "volume": float(tick.get("volume", 0.0)),
        })
        self._tick_counts[key] += 1

        # Invalidate cache on new tick
        self._cache.pop(key, None)

    def compute_features(self, exchange: str, symbol: str) -> dict:
        """
        Compute (or return cached) features for a symbol.

        Returns empty dict if fewer than 20 ticks available.
        Features are cached for cache_ttl_s seconds.
        """
        key = f"{exchange}:{symbol}"

        # Return cache if fresh
        now = time.monotonic()
        if key in self._cache:
            cached_at, cached_features = self._cache[key]
            if now - cached_at < self._cache_ttl:
                return cached_features

        buf = self._buffers.get(key)
        if not buf or len(buf) < 20:
            return {}

        df = self._buffer_to_df(buf)
        if df is None or len(df) < 5:
            return {}

        features: dict = {
            "_symbol": symbol,
            "_exchange": exchange,
            "_tick_count": self._tick_counts.get(key, 0),
            "_computed_at": time.time(),
        }

        try:
            features.update(compute_technical_features(df))
        except Exception as e:
            logger.warning("Technical features failed", symbol=key, error=str(e))

        try:
            features.update(compute_microstructure_features(df))
        except Exception as e:
            logger.warning("Microstructure features failed", symbol=key, error=str(e))

        try:
            features.update(compute_cross_asset_features(key, self._get_all_dfs()))
        except Exception as e:
            logger.warning("Cross-asset features failed", symbol=key, error=str(e))

        try:
            features.update(compute_momentum_features(df))
        except Exception as e:
            logger.warning("Momentum features failed", symbol=key, error=str(e))

        self._cache[key] = (now, features)

        n_features = sum(1 for k in features if not k.startswith("_"))
        logger.debug("Features computed", symbol=key, count=n_features)

        return features

    def get_features(
        self, exchange: str, symbol: str, timestamp: Optional[str] = None
    ) -> dict:
        """Alias for compute_features (public API matching the plan spec)."""
        return self.compute_features(exchange, symbol)

    def all_symbols(self) -> list[str]:
        """Return all buffered symbol keys."""
        return list(self._buffers.keys())

    def tick_count(self, exchange: str, symbol: str) -> int:
        return self._tick_counts.get(f"{exchange}:{symbol}", 0)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _buffer_to_df(self, buf: deque[dict]) -> Optional[pd.DataFrame]:
        """Convert tick buffer to a cleaned OHLCV DataFrame with DatetimeIndex."""
        try:
            df = pd.DataFrame(list(buf))
            for col in ("open", "high", "low", "close", "volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # Drop rows where close is NaN or zero
            df = df.dropna(subset=["close"])
            df = df[df["close"] > 0]

            if df.empty:
                return None

            # Build DatetimeIndex from timestamp field if available
            if "timestamp" in df.columns and df["timestamp"].notna().any():
                try:
                    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
                    df = df.set_index("timestamp").sort_index()
                except Exception:
                    df = df.drop(columns=["timestamp"], errors="ignore")
            else:
                df = df.drop(columns=["timestamp"], errors="ignore")

            return df

        except Exception as e:
            logger.warning("Buffer to DataFrame failed", error=str(e))
            return None

    def _get_all_dfs(self) -> dict[str, pd.DataFrame]:
        """Get DataFrames for all buffered symbols (for cross-asset computation)."""
        result = {}
        for key, buf in self._buffers.items():
            if len(buf) >= 10:
                df = self._buffer_to_df(buf)
                if df is not None:
                    result[key] = df
        return result
