"""
Momentum feature engineering — 12+ features.

Features:
  Cumulative returns at 5 horizons (5, 10, 20, 60, 300 bars)
  Z-score vs SMA(20) and SMA(50)
  Rate of Change at 3 horizons
  Volume momentum ratio (current vs 20-bar avg)
  Acceleration (ROC of ROC)
  Trend strength (R² of linear regression on close)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

_MIN_BARS = 5


def compute_momentum_features(df: pd.DataFrame) -> dict[str, float]:
    """
    Compute momentum features from an OHLCV DataFrame.
    """
    if len(df) < _MIN_BARS:
        return {}

    feat: dict[str, float] = {}

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    n = len(close)

    # ── Cumulative returns at multiple horizons ───────────────────────────────
    for period, label in ((5, "5b"), (10, "10b"), (20, "20b"), (60, "60b"), (300, "300b")):
        p = min(period, n - 1)
        if p > 0 and float(close.iloc[-1 - p]) > 0:
            ret = float(close.iloc[-1] / close.iloc[-1 - p]) - 1.0
            feat[f"mom_return_{label}"] = round(ret, 8)

    # ── Z-score vs SMA(20) and SMA(50) ───────────────────────────────────────
    current = float(close.iloc[-1])
    for window, label in ((20, "20"), (50, "50")):
        w = min(window, n)
        if w >= 5:
            window_prices = close.iloc[-w:]
            sma = float(window_prices.mean())
            std = float(window_prices.std())
            if std > 0:
                feat[f"mom_zscore_sma{label}"] = round((current - sma) / std, 6)
            feat[f"mom_sma{label}_dist_pct"] = round((current - sma) / sma, 6) if sma > 0 else 0.0

    # ── Rate of Change (%) ────────────────────────────────────────────────────
    for period, label in ((5, "5b"), (10, "10b"), (20, "20b")):
        p = min(period, n - 1)
        if p > 0 and float(close.iloc[-1 - p]) > 0:
            roc = float((close.iloc[-1] - close.iloc[-1 - p]) / close.iloc[-1 - p] * 100)
            feat[f"mom_roc_{label}"] = round(roc, 6)

    # ── Volume Momentum Ratio ─────────────────────────────────────────────────
    if n >= 20:
        avg_vol = float(volume.iloc[-20:].mean())
        current_vol = float(volume.iloc[-1])
        if avg_vol > 0:
            feat["mom_vol_ratio_20b"] = round(current_vol / avg_vol, 6)

    # ── Momentum Acceleration (ROC of 5b ROC) ────────────────────────────────
    if n >= 10 and float(close.iloc[-6]) > 0 and float(close.iloc[-11]) > 0:
        roc_now = float((close.iloc[-1] - close.iloc[-6]) / close.iloc[-6] * 100)
        roc_prev = float((close.iloc[-6] - close.iloc[-11]) / close.iloc[-11] * 100)
        feat["mom_acceleration"] = round(roc_now - roc_prev, 6)

    # ── Trend Strength (R² of linear fit on last 20 bars) ────────────────────
    w = min(20, n)
    if w >= 5:
        prices = close.iloc[-w:].values
        x = np.arange(w, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            coeffs = np.polyfit(x, prices, 1)
            predicted = np.polyval(coeffs, x)
            ss_res = float(np.sum((prices - predicted) ** 2))
            ss_tot = float(np.sum((prices - prices.mean()) ** 2))
            r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
        feat["mom_trend_r2"] = round(max(0.0, min(1.0, r_squared)), 6)
        feat["mom_trend_slope_pct"] = round(float(coeffs[0]) / float(prices.mean()) * 100, 6) if prices.mean() > 0 else 0.0

    return feat
