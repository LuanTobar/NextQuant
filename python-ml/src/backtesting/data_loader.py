"""
Historical data loader for the backtesting engine.

Sources (in priority order):
  1. yfinance  — 6-month daily OHLCV bars (requires internet)
  2. Synthetic  — deterministic fallback for offline / test use

Returns tick dicts compatible with the live MLService format:
  {symbol, exchange, open, high, low, close, volume, timestamp}
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import numpy as np

logger = logging.getLogger(__name__)

# Period → approximate trading days
_PERIOD_DAYS: dict[str, int] = {
    "1m":  21,
    "3m":  63,
    "6m": 126,
    "1y": 252,
    "2y": 504,
}


def load_bars(
    symbol: str,
    period: str = "6m",
    exchange: str = "US",
    interval: str = "1d",
) -> list[dict]:
    """
    Load historical OHLCV bars as tick dicts (oldest first).

    Args:
        symbol:   Ticker, e.g. "AAPL"
        period:   "1m" | "3m" | "6m" | "1y" | "2y"
        exchange: Exchange label stored in returned dicts
        interval: yfinance interval ("1d", "1h", "1wk")

    Returns:
        List of tick dicts with keys:
          symbol, exchange, open, high, low, close, volume, timestamp
    """
    try:
        bars = _from_yfinance(symbol, period, exchange, interval)
        if bars:
            return bars
        logger.warning("yfinance returned empty data — using synthetic fallback",
                       extra={"symbol": symbol})
    except Exception as exc:
        logger.warning("yfinance failed (%s) — using synthetic fallback", exc,
                       extra={"symbol": symbol})

    return _synthetic(symbol, period, exchange)


# ── Private helpers ────────────────────────────────────────────────────────────

def _from_yfinance(symbol: str, period: str, exchange: str, interval: str) -> list[dict]:
    import yfinance as yf  # lazy import — optional dependency

    # yfinance uses "6mo" not "6m"
    yf_period = (period[:-1] + "mo") if period.endswith("m") and not period.endswith("mo") else period

    df = yf.Ticker(symbol).history(period=yf_period, interval=interval, auto_adjust=True)
    if df.empty:
        return []

    # Normalise timezone to UTC
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    else:
        df.index = df.index.tz_convert("UTC")

    bars = []
    for ts, row in df.iterrows():
        dt = ts.to_pydatetime()
        bars.append({
            "symbol":    symbol,
            "exchange":  exchange,
            "open":      float(row["Open"]),
            "high":      float(row["High"]),
            "low":       float(row["Low"]),
            "close":     float(row["Close"]),
            "volume":    float(row.get("Volume", 0) or 0),
            "timestamp": dt.isoformat(),
        })
    return bars


def _synthetic(symbol: str, period: str, exchange: str) -> list[dict]:
    """
    Deterministic synthetic OHLCV bars.

    Generates a mildly-trending asset suitable for testing
    and offline development.  Seed is derived from the symbol
    so different symbols produce different paths.
    """
    n   = _PERIOD_DAYS.get(period, 126)
    rng = np.random.default_rng(abs(hash(symbol)) % (2 ** 31))

    trend   = 0.0003    # ≈ 7.6% annualised expected return
    vol     = 0.010     # ≈ 15.9% annualised vol
    returns = rng.normal(trend, vol, n)
    prices  = np.maximum(100.0 * np.cumprod(1 + returns), 1.0)

    start = datetime(2025, 9, 1, 14, 30, tzinfo=timezone.utc)
    bars  = []
    for i, p in enumerate(prices):
        noise = float(rng.uniform(-0.002, 0.002))
        bars.append({
            "symbol":    symbol,
            "exchange":  exchange,
            "open":      round(p * (1 + noise),               4),
            "high":      round(p * (1 + abs(noise) + 0.003),  4),
            "low":       round(p * (1 - abs(noise) - 0.003),  4),
            "close":     round(p,                              4),
            "volume":    float(rng.integers(500_000, 5_000_000)),
            "timestamp": (start + timedelta(days=i)).isoformat(),
        })
    return bars
