"""
Cross-asset feature engineering — 15+ features.

For each tracked benchmark (SPY, BTC, TLT, DXY-proxy, VIX-proxy):
  - Rolling 30-bar correlation
  - Rolling beta (covariance / benchmark variance)

Also computes:
  - Relative strength vs own 30-bar mean (z-score style)
  - Volume-weighted spread vs VWAP
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)

# Canonical benchmark keys (exchange:symbol format)
_BENCHMARKS = [
    "US:SPY",
    "CRYPTO:BTCUSDT",
    "US:TLT",
    "US:QQQ",
    "US:GLD",
]

_WINDOW = 30
_MIN_OVERLAP = 10


def compute_cross_asset_features(
    symbol_key: str,
    all_dfs: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """
    Compute cross-asset features for symbol_key using other symbols as benchmarks.

    Args:
        symbol_key: 'EXCHANGE:SYMBOL' of the target asset
        all_dfs: dict of all buffered DataFrames keyed by 'EXCHANGE:SYMBOL'
    """
    feat: dict[str, float] = {}

    target_df = all_dfs.get(symbol_key)
    if target_df is None or len(target_df) < _MIN_OVERLAP:
        return feat

    target_returns = (
        target_df["close"].astype(float).pct_change().dropna()
    )

    for bench_key in _BENCHMARKS:
        if bench_key == symbol_key:
            continue
        bench_df = all_dfs.get(bench_key)
        if bench_df is None or len(bench_df) < _MIN_OVERLAP:
            continue

        bench_returns = bench_df["close"].astype(float).pct_change().dropna()

        # Align lengths (take most recent common window)
        n = min(len(target_returns), len(bench_returns), _WINDOW)
        if n < _MIN_OVERLAP:
            continue

        t = target_returns.iloc[-n:].values
        b = bench_returns.iloc[-n:].values

        # Skip if constant (no variance)
        if np.std(b) == 0 or np.std(t) == 0:
            continue

        bench_label = bench_key.replace(":", "_").lower()

        # Correlation
        corr = float(np.corrcoef(t, b)[0, 1])
        if not np.isnan(corr):
            feat[f"ca_corr_{bench_label}"] = round(corr, 6)

        # Beta (target vs benchmark)
        beta = float(np.cov(t, b)[0, 1] / np.var(b))
        if not np.isnan(beta) and not np.isinf(beta):
            feat[f"ca_beta_{bench_label}"] = round(beta, 6)

    # ── Relative strength (target vs its own 30-bar SMA) ─────────────────────
    close = target_df["close"].astype(float)
    if len(close) >= _WINDOW:
        sma30 = float(close.iloc[-_WINDOW:].mean())
        std30 = float(close.iloc[-_WINDOW:].std())
        if sma30 > 0 and std30 > 0:
            feat["ca_rel_strength_sma30"] = round(
                (float(close.iloc[-1]) - sma30) / std30, 6
            )

    # ── Price spread vs VWAP (last 30 bars) ──────────────────────────────────
    if len(target_df) >= _WINDOW:
        window_df = target_df.iloc[-_WINDOW:]
        vol = window_df["volume"].astype(float)
        total_vol = float(vol.sum())
        if total_vol > 0:
            vwap = float((window_df["close"].astype(float) * vol).sum() / total_vol)
            price = float(target_df["close"].iloc[-1])
            feat["ca_vwap_spread_30b"] = round((price - vwap) / vwap, 6) if vwap > 0 else 0.0

    return feat
