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
import ta.momentum as tam
import ta.trend as tat
import ta.volatility as tav
import ta.volume as tavol

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
        try:
            v = _safe_last(tam.RSIIndicator(close, window=period, fillna=False).rsi())
            if v is not None:
                feat[f"{prefix}_rsi_{period}"] = v
        except Exception:
            pass

    # ── MACD ─────────────────────────────────────────────────────────────────
    try:
        macd_ind = tat.MACD(close, window_slow=26, window_fast=12, window_sign=9, fillna=False)
        for series, key in (
            (macd_ind.macd(), "macd"),
            (macd_ind.macd_diff(), "macd_hist"),
            (macd_ind.macd_signal(), "macd_signal"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    try:
        bb = tav.BollingerBands(close, window=20, window_dev=2, fillna=False)
        bb_lower = bb.bollinger_lband()
        bb_mid   = bb.bollinger_mavg()
        bb_upper = bb.bollinger_hband()
        bb_wband = bb.bollinger_wband()
        bb_pband = bb.bollinger_pband()
        for series, key in (
            (bb_lower, "bb_lower"), (bb_mid, "bb_mid"), (bb_upper, "bb_upper"),
            (bb_wband, "bb_bandwidth"), (bb_pband, "bb_pct_b"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── ATR ───────────────────────────────────────────────────────────────────
    for period in (14, 7):
        try:
            key = f"{prefix}_atr_{period}"
            v = _safe_last(tav.AverageTrueRange(high, low, close, window=period, fillna=False).average_true_range())
            if v is not None:
                feat[key] = v
        except Exception:
            pass

    # ── OBV + momentum ───────────────────────────────────────────────────────
    try:
        obv = tavol.OnBalanceVolumeIndicator(close, volume, fillna=False).on_balance_volume()
        if obv is not None and len(obv) >= 5:
            v = _safe_last(obv)
            if v is not None:
                feat[f"{prefix}_obv"] = v
            obv_clean = obv.dropna()
            if len(obv_clean) >= 5:
                feat[f"{prefix}_obv_momentum_5"] = float(obv_clean.iloc[-1] - obv_clean.iloc[-5])
    except Exception:
        pass

    # ── ADX ───────────────────────────────────────────────────────────────────
    try:
        adx_ind = tat.ADXIndicator(high, low, close, window=14, fillna=False)
        for series, key in (
            (adx_ind.adx(), "adx"),
            (adx_ind.adx_pos(), "adx_di_plus"),
            (adx_ind.adx_neg(), "adx_di_minus"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── Stochastic ────────────────────────────────────────────────────────────
    try:
        stoch = tam.StochasticOscillator(high, low, close, window=14, smooth_window=3, fillna=False)
        for series, key in (
            (stoch.stoch(), "stoch_k"),
            (stoch.stoch_signal(), "stoch_d"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── Williams %R ───────────────────────────────────────────────────────────
    try:
        v = _safe_last(tam.WilliamsRIndicator(high, low, close, lbp=14, fillna=False).williams_r())
        if v is not None:
            feat[f"{prefix}_williams_r"] = v
    except Exception:
        pass

    # ── CCI ───────────────────────────────────────────────────────────────────
    try:
        v = _safe_last(tat.CCIIndicator(high, low, close, window=20, fillna=False).cci())
        if v is not None:
            feat[f"{prefix}_cci"] = v
    except Exception:
        pass

    # ── MFI ───────────────────────────────────────────────────────────────────
    try:
        v = _safe_last(tavol.MFIIndicator(high, low, close, volume, window=14, fillna=False).money_flow_index())
        if v is not None:
            feat[f"{prefix}_mfi"] = v
    except Exception:
        pass

    # ── RSI extra period ─────────────────────────────────────────────────────
    try:
        v = _safe_last(tam.RSIIndicator(close, window=7, fillna=False).rsi())
        if v is not None:
            feat[f"{prefix}_rsi_7"] = v
    except Exception:
        pass

    # ── EMAs + distance-to-EMA ───────────────────────────────────────────────
    current = float(close.iloc[-1])
    for period in (5, 10, 20, 50):
        try:
            v = _safe_last(tat.EMAIndicator(close, window=period, fillna=False).ema_indicator())
            if v is not None and v > 0:
                feat[f"{prefix}_ema_{period}"] = v
                feat[f"{prefix}_ema_{period}_dist_pct"] = round((current - v) / v, 6)
        except Exception:
            pass

    # ── SMAs + distance-to-SMA ───────────────────────────────────────────────
    for period in (10, 20, 50):
        try:
            v = _safe_last(tat.SMAIndicator(close, window=period, fillna=False).sma_indicator())
            if v is not None and v > 0:
                feat[f"{prefix}_sma_{period}"] = v
                feat[f"{prefix}_sma_{period}_dist_pct"] = round((current - v) / v, 6)
        except Exception:
            pass

    # ── Chaikin Money Flow (CMF) ──────────────────────────────────────────────
    try:
        v = _safe_last(tavol.ChaikinMoneyFlowIndicator(high, low, close, volume, window=20, fillna=False).chaikin_money_flow())
        if v is not None:
            feat[f"{prefix}_cmf"] = v
    except Exception:
        pass

    # ── Keltner Channel ───────────────────────────────────────────────────────
    try:
        kc = tav.KeltnerChannel(high, low, close, window=20, fillna=False)
        for series, key in (
            (kc.keltner_channel_lband(), "kc_lower"),
            (kc.keltner_channel_mband(), "kc_mid"),
            (kc.keltner_channel_hband(), "kc_upper"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── Donchian Channel ──────────────────────────────────────────────────────
    try:
        dc = tav.DonchianChannel(high, low, close, window=20, fillna=False)
        for series, key in (
            (dc.donchian_channel_lband(), "dc_lower"),
            (dc.donchian_channel_mband(), "dc_mid"),
            (dc.donchian_channel_hband(), "dc_upper"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

    # ── Aroon ─────────────────────────────────────────────────────────────────
    try:
        aroon = tat.AroonIndicator(high, low, window=14, fillna=False)
        for series, key in (
            (aroon.aroon_down(), "aroon_down"),
            (aroon.aroon_up(), "aroon_up"),
        ):
            v = _safe_last(series)
            if v is not None:
                feat[f"{prefix}_{key}"] = v
    except Exception:
        pass

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
