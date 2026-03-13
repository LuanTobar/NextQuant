"""
Microstructure feature engineering — 20+ features.

Features:
  Volume imbalance (directional flow estimate)
  VWAP + VWAP deviation
  Realized volatility (3 windows)
  Parkinson volatility estimator (uses high-low range)
  Garman-Klass volatility estimator
  Log returns at 5 horizons
  Rolling return skewness + kurtosis (last 20 bars)
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

_MIN_BARS = 5


def compute_microstructure_features(df: pd.DataFrame) -> dict[str, float]:
    """
    Compute microstructure features from an OHLCV DataFrame.
    Index can be datetime or integer; no resampling required.
    """
    if len(df) < _MIN_BARS:
        return {}

    feat: dict[str, float] = {}

    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    open_ = df["open"].astype(float)
    volume = df["volume"].astype(float)

    # ── Volume Imbalance (tick direction proxy) ───────────────────────────────
    returns = close.pct_change()
    buy_vol = np.where(returns > 0, volume, np.where(returns < 0, 0.0, volume * 0.5))
    total_vol = float(volume.sum())
    if total_vol > 0:
        feat["ms_volume_imbalance"] = round(float(np.sum(buy_vol)) / total_vol, 6)
    else:
        feat["ms_volume_imbalance"] = 0.5

    # ── VWAP + Deviation ─────────────────────────────────────────────────────
    vwap = float((close * volume).sum() / total_vol) if total_vol > 0 else float(close.mean())
    current_price = float(close.iloc[-1])
    feat["ms_vwap"] = round(vwap, 6)
    feat["ms_vwap_deviation"] = round((current_price - vwap) / vwap, 6) if vwap > 0 else 0.0

    # ── Realized Volatility (multiple windows) ────────────────────────────────
    log_returns = np.log(close / close.shift(1)).dropna()
    for window, label in ((5, "5b"), (60, "60b"), (300, "300b")):
        w = min(window, len(log_returns))
        if w >= 2:
            rv = float(np.sqrt(np.sum(log_returns.iloc[-w:] ** 2)))
            feat[f"ms_realized_vol_{label}"] = round(rv, 8)

    # ── Parkinson Estimator (high-low range) ──────────────────────────────────
    if len(df) >= 2:
        with np.errstate(divide="ignore", invalid="ignore"):
            hl_log = np.log(high / low)
            hl_log = hl_log.replace([np.inf, -np.inf], np.nan).dropna()
        if len(hl_log) >= 2:
            parkinson = float(np.sqrt((1.0 / (4.0 * np.log(2))) * (hl_log ** 2).mean()))
            feat["ms_parkinson_vol"] = round(parkinson, 8)

    # ── Garman-Klass Estimator ────────────────────────────────────────────────
    if len(df) >= 2:
        with np.errstate(divide="ignore", invalid="ignore"):
            gk_hl = 0.5 * np.log(high / low) ** 2
            gk_co = (2 * np.log(2) - 1) * np.log(close / open_) ** 2
            gk = (gk_hl - gk_co).replace([np.inf, -np.inf], np.nan).dropna()
        if len(gk) >= 2:
            feat["ms_garman_klass_vol"] = round(float(np.sqrt(gk.mean())), 8)

    # ── Log Returns at multiple horizons ─────────────────────────────────────
    for horizon, label in ((1, "1b"), (5, "5b"), (15, "15b"), (60, "60b"), (300, "300b")):
        h = min(horizon, len(close) - 1)
        if h > 0 and float(close.iloc[-1 - h]) > 0:
            lr = float(np.log(close.iloc[-1] / close.iloc[-1 - h]))
            feat[f"ms_log_return_{label}"] = round(lr, 8)

    # ── Rolling Skewness + Kurtosis (last 20 bars) ────────────────────────────
    if len(log_returns) >= 10:
        recent = log_returns.iloc[-20:]
        skew = float(recent.skew())
        kurt = float(recent.kurtosis())
        if not np.isnan(skew):
            feat["ms_return_skewness"] = round(skew, 6)
        if not np.isnan(kurt):
            feat["ms_return_kurtosis"] = round(kurt, 6)

    # ── Return Autocorrelation (lag 1 and lag 5) ─────────────────────────────
    if len(log_returns) >= 10:
        lr_vals = log_returns.values
        if len(lr_vals) > 1:
            ac1 = float(np.corrcoef(lr_vals[:-1], lr_vals[1:])[0, 1])
            if np.isfinite(ac1):
                feat["ms_autocorr_lag1"] = round(ac1, 6)
        if len(lr_vals) > 5:
            ac5 = float(np.corrcoef(lr_vals[:-5], lr_vals[5:])[0, 1])
            if np.isfinite(ac5):
                feat["ms_autocorr_lag5"] = round(ac5, 6)

    # ── Amihud Illiquidity (|return| / dollar_volume) ─────────────────────────
    if len(log_returns) >= 5 and total_vol > 0:
        n = min(20, len(log_returns))
        abs_rets = log_returns.iloc[-n:].abs().values
        vols_n = volume.iloc[-n:].replace(0, np.nan).values
        with np.errstate(divide="ignore", invalid="ignore"):
            illiq_vals = abs_rets / vols_n
        illiq_vals = illiq_vals[np.isfinite(illiq_vals)]
        if len(illiq_vals) > 0:
            feat["ms_amihud_illiq"] = round(float(np.mean(illiq_vals)), 10)

    # ── High-Low Range ratio (normalized spread proxy) ────────────────────────
    if len(df) >= 5:
        hl_mean = float((high - low).iloc[-20:].mean())
        price = float(close.iloc[-1])
        if price > 0:
            feat["ms_hl_range_ratio"] = round(hl_mean / price, 6)

    # ── Tick Direction (signed order flow proxy) ──────────────────────────────
    if len(close) >= 5:
        diffs = close.diff().iloc[-20:].dropna()
        up_t = int((diffs > 0).sum())
        dn_t = int((diffs < 0).sum())
        total_t = up_t + dn_t
        if total_t > 0:
            feat["ms_tick_direction"] = round((up_t - dn_t) / total_t, 6)

    return feat
