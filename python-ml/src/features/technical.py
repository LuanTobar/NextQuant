"""
Technical feature engineering — 45+ indicators across multiple timeframes.

Timeframes computed (if enough ticks available):
  tf_1m  — 1-minute bars (resampled from 1Hz ticks)
  tf_5m  — 5-minute bars
  tf_1h  — 1-hour bars
  tf_raw — raw 1Hz ticks (always computed)

Indicators per timeframe (45+ total):
  RSI(7,14,28), MACD(12/26/9), Bollinger(20,2σ), ATR(7,14),
  OBV + OBV momentum, ADX(14) + DI+/DI-, Stochastic(14,3),
  Williams %R(14), CCI(20), MFI(14),
  EMA(5,10,20,50) + distance-to-EMA,
  SMA(10,20,50) + distance-to-SMA,
  VWAP distance, Chaikin Money Flow (CMF),
  Keltner Channel (upper/lower/mid),
  Donchian Channel (upper/lower/mid),
  Aroon (up/down)
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
import pandas_ta as ta

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Minimum bars required to compute indicators reliably
_MIN_BARS = 30


def _safe_last(series: pd.Series | None) -> float | None:
    """Return last non-NaN value or None."""
    if series is None or series.empty:
        return None
    val = series.dropna()
    return float(val.iloc[-1]) if not val.empty else None


def _compute_indicators(df: pd.DataFrame, prefix: str) -> dict[str, float]:
    """
    Compute all technical indicators on an OHLCV DataFrame.
    Returns a flat dict with keys like '<prefix>_rsi_14'.
    """
    if len(df) < _MIN_BARS:
        return {}

    feat: dict[str, Any] = {}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"].astype(float)

    # ── RSI ──────────────────────────────────────────────────────────────────
    for period in (14, 28):
        v = _safe_last(ta.rsi(close, length=period))
        if v is not None:
            feat[f"{prefix}_rsi_{period}"] = v

    # ── MACD ─────────────────────────────────────────────────────────────────
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    if macd_df is not None and len(macd_df):
        for col, key in zip(macd_df.columns[:3], ("macd", "macd_hist", "macd_signal")):
            v = _safe_last(macd_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_df = ta.bbands(close, length=20, std=2)
    if bb_df is not None and len(bb_df):
        cols = bb_df.columns.tolist()
        keys = ("bb_lower", "bb_mid", "bb_upper", "bb_bandwidth", "bb_pct_b")
        for col, key in zip(cols[:5], keys):
            v = _safe_last(bb_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── ATR ───────────────────────────────────────────────────────────────────
    v = _safe_last(ta.atr(high, low, close, length=14))
    if v is not None:
        feat[f"{prefix}_atr_14"] = v

    # ── OBV + momentum ───────────────────────────────────────────────────────
    obv = ta.obv(close, volume)
    if obv is not None and len(obv) >= 5:
        v = _safe_last(obv)
        if v is not None:
            feat[f"{prefix}_obv"] = v
        obv_clean = obv.dropna()
        if len(obv_clean) >= 5:
            feat[f"{prefix}_obv_momentum_5"] = float(obv_clean.iloc[-1] - obv_clean.iloc[-5])

    # ── ADX ───────────────────────────────────────────────────────────────────
    adx_df = ta.adx(high, low, close, length=14)
    if adx_df is not None and len(adx_df):
        for col, key in zip(adx_df.columns[:3], ("adx", "adx_di_plus", "adx_di_minus")):
            v = _safe_last(adx_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── Stochastic ────────────────────────────────────────────────────────────
    stoch_df = ta.stoch(high, low, close)
    if stoch_df is not None and len(stoch_df):
        for col, key in zip(stoch_df.columns[:2], ("stoch_k", "stoch_d")):
            v = _safe_last(stoch_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── Williams %R ───────────────────────────────────────────────────────────
    v = _safe_last(ta.willr(high, low, close, length=14))
    if v is not None:
        feat[f"{prefix}_williams_r"] = v

    # ── CCI ───────────────────────────────────────────────────────────────────
    v = _safe_last(ta.cci(high, low, close, length=20))
    if v is not None:
        feat[f"{prefix}_cci"] = v

    # ── MFI ───────────────────────────────────────────────────────────────────
    v = _safe_last(ta.mfi(high, low, close, volume, length=14))
    if v is not None:
        feat[f"{prefix}_mfi"] = v

    # ── RSI extra period ─────────────────────────────────────────────────────
    v = _safe_last(ta.rsi(close, length=7))
    if v is not None:
        feat[f"{prefix}_rsi_7"] = v

    # ── ATR extra period ──────────────────────────────────────────────────────
    v = _safe_last(ta.atr(high, low, close, length=7))
    if v is not None:
        feat[f"{prefix}_atr_7"] = v

    # ── EMAs + distance-to-EMA ───────────────────────────────────────────────
    current = float(close.iloc[-1])
    for period in (5, 10, 20, 50):
        ema = ta.ema(close, length=period)
        v = _safe_last(ema)
        if v is not None and v > 0:
            feat[f"{prefix}_ema_{period}"] = v
            feat[f"{prefix}_ema_{period}_dist_pct"] = round((current - v) / v, 6)

    # ── SMAs + distance-to-SMA ───────────────────────────────────────────────
    for period in (10, 20, 50):
        sma = ta.sma(close, length=period)
        v = _safe_last(sma)
        if v is not None and v > 0:
            feat[f"{prefix}_sma_{period}"] = v
            feat[f"{prefix}_sma_{period}_dist_pct"] = round((current - v) / v, 6)

    # ── Chaikin Money Flow (CMF) ──────────────────────────────────────────────
    v = _safe_last(ta.cmf(high, low, close, volume, length=20))
    if v is not None:
        feat[f"{prefix}_cmf"] = v

    # ── Keltner Channel ───────────────────────────────────────────────────────
    kc_df = ta.kc(high, low, close, length=20)
    if kc_df is not None and len(kc_df):
        for col, key in zip(kc_df.columns[:3], ("kc_lower", "kc_mid", "kc_upper")):
            v = _safe_last(kc_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── Donchian Channel ──────────────────────────────────────────────────────
    dc_df = ta.donchian(high, low, length=20)
    if dc_df is not None and len(dc_df):
        for col, key in zip(dc_df.columns[:3], ("dc_lower", "dc_mid", "dc_upper")):
            v = _safe_last(dc_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    # ── Aroon ─────────────────────────────────────────────────────────────────
    aroon_df = ta.aroon(high, low, length=14)
    if aroon_df is not None and len(aroon_df):
        for col, key in zip(aroon_df.columns[:2], ("aroon_down", "aroon_up")):
            v = _safe_last(aroon_df[col])
            if v is not None:
                feat[f"{prefix}_{key}"] = v

    return {k: round(v, 6) for k, v in feat.items()}


def _resample_ohlcv(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    """Aggregate 1Hz tick data into OHLCV candles at the given frequency."""
    resampled = (
        df.resample(freq)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["close"])
    )
    return resampled


def compute_technical_features(df: pd.DataFrame) -> dict[str, float]:
    """
    Entry point: compute technical features from a raw 1Hz OHLCV DataFrame.
    Timestamps must be in the index (DatetimeTzAware or Naive UTC).
    """
    features: dict[str, float] = {}

    has_time_index = isinstance(df.index, pd.DatetimeIndex)

    if has_time_index and len(df) >= _MIN_BARS:
        for tf_name, freq in (("1m", "1min"), ("5m", "5min"), ("1h", "1h")):
            try:
                resampled = _resample_ohlcv(df, freq)
                if len(resampled) >= _MIN_BARS:
                    features.update(_compute_indicators(resampled, prefix=f"tf_{tf_name}"))
            except Exception:
                pass  # insufficient data for this timeframe

    # Always compute on raw ticks with reduced window expectations
    if len(df) >= _MIN_BARS:
        features.update(_compute_indicators(df, prefix="tf_raw"))

    return features
