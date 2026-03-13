"""
Granger Causality Filter.

Tests whether time series X Granger-causes time series Y using the
standard F-test implemented in statsmodels.

The null hypothesis is that X does NOT Granger-cause Y (i.e. past values
of X add no predictive power for Y beyond past values of Y alone).

Usage:
    result = granger_test(x, y, max_lag=5)
    # result["is_significant"]  → bool
    # result["best_lag"]        → int
    # result["p_value"]         → float
    # result["f_stat"]          → float
    # result["strength"]        → float in [-1, 1]  (signed correlation weight)
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np


def granger_test(
    x: np.ndarray,
    y: np.ndarray,
    max_lag: int = 5,
    significance: float = 0.05,
) -> dict:
    """
    Test whether x Granger-causes y.

    Args:
        x:            predictor series (1-D, equal length to y)
        y:            outcome series (1-D)
        max_lag:      maximum lag order to test
        significance: p-value threshold for significance

    Returns:
        {
          "is_significant": bool,
          "best_lag": int,       # lag with lowest p-value
          "p_value": float,
          "f_stat": float,
          "strength": float,     # signed: positive = positive Granger effect
        }
    """
    if len(x) != len(y) or len(x) < max_lag + 10:
        return _empty_result()

    try:
        from statsmodels.tsa.stattools import grangercausalitytests

        data = np.column_stack([y, x])   # statsmodels expects [outcome, predictor]

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            results = grangercausalitytests(data, maxlag=max_lag, verbose=False)

        # Find the lag with the minimum p-value (F-test)
        best_lag, best_p, best_f = max_lag, 1.0, 0.0
        for lag, res in results.items():
            p = float(res[0]["ssr_ftest"][1])   # p-value from F-test
            f = float(res[0]["ssr_ftest"][0])   # F-statistic
            if p < best_p:
                best_p, best_f, best_lag = p, f, lag

        # Signed strength: correlation between lagged x and y residuals
        if best_lag <= len(x) - 1:
            x_lag = x[:-best_lag] if best_lag > 0 else x
            y_fwd = y[best_lag:] if best_lag > 0 else y
            min_len = min(len(x_lag), len(y_fwd))
            if min_len > 2:
                corr = float(np.corrcoef(x_lag[:min_len], y_fwd[:min_len])[0, 1])
                strength = round(corr if np.isfinite(corr) else 0.0, 4)
            else:
                strength = 0.0
        else:
            strength = 0.0

        return {
            "is_significant": best_p < significance,
            "best_lag": best_lag,
            "p_value": round(best_p, 6),
            "f_stat": round(best_f, 4),
            "strength": strength,
        }

    except Exception:
        return _empty_result()


def granger_batch(
    series_dict: dict[str, np.ndarray],
    target_key: str,
    max_lag: int = 5,
    significance: float = 0.05,
) -> list[dict]:
    """
    Run Granger tests from all series in series_dict → target_key.

    Returns a list of significant relationships sorted by p-value.
    """
    y = series_dict.get(target_key)
    if y is None or len(y) < max_lag + 10:
        return []

    relationships = []
    for key, x in series_dict.items():
        if key == target_key or len(x) != len(y):
            continue
        result = granger_test(x, y, max_lag=max_lag, significance=significance)
        if result["is_significant"]:
            relationships.append({
                "from": key,
                "to": target_key,
                "method": "granger",
                "p_value": result["p_value"],
                "f_stat": result["f_stat"],
                "lag": result["best_lag"],
                "strength": result["strength"],
            })

    return sorted(relationships, key=lambda r: r["p_value"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _empty_result() -> dict:
    return {
        "is_significant": False,
        "best_lag": 1,
        "p_value": 1.0,
        "f_stat": 0.0,
        "strength": 0.0,
    }
