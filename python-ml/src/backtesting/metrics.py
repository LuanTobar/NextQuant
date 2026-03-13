"""
Performance metrics for the backtesting engine.

All functions are pure (no side-effects) and accept NumPy arrays
or plain Python lists.  Annualisation assumes calendar-day input
unless `periods_per_year` is overridden.
"""

from __future__ import annotations

import numpy as np


# ── Core metrics ──────────────────────────────────────────────────────────────

def sharpe_ratio(
    returns: np.ndarray,
    rf: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Annualised Sharpe ratio.

    Args:
        returns:          Array of period returns (not cumulative).
        rf:               Annual risk-free rate (default 0).
        periods_per_year: Number of periods per year (252 for daily bars).
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    excess = r - rf / periods_per_year
    std = np.std(excess, ddof=1)
    if std < 1e-12:
        return 0.0
    return float(np.mean(excess) / std * np.sqrt(periods_per_year))


def sortino_ratio(
    returns: np.ndarray,
    rf: float = 0.0,
    periods_per_year: float = 252.0,
) -> float:
    """Annualised Sortino ratio (downside deviation only in denominator).

    Returns 0.0 when there are no negative periods (rather than ∞).
    """
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return 0.0
    excess   = r - rf / periods_per_year
    downside = excess[excess < 0]
    if len(downside) == 0:
        return 0.0
    downside_std = float(np.sqrt(np.mean(downside ** 2)))
    if downside_std < 1e-12:
        return 0.0
    return float(np.mean(excess) / downside_std * np.sqrt(periods_per_year))


def max_drawdown(equity_curve: np.ndarray) -> float:
    """Maximum peak-to-trough drawdown as a negative fraction.

    E.g. a 25% drawdown is returned as -0.25.
    """
    eq = np.asarray(equity_curve, dtype=float)
    if len(eq) < 2:
        return 0.0
    peak = np.maximum.accumulate(eq)
    # Avoid division by zero for zero-equity periods
    dd = np.where(peak > 0, (eq - peak) / peak, 0.0)
    return float(np.min(dd))


def calmar_ratio(
    returns: np.ndarray,
    equity_curve: np.ndarray,
    periods_per_year: float = 252.0,
) -> float:
    """Calmar ratio = annualised return / |max drawdown|.

    Returns 0.0 when max drawdown is negligible.
    """
    mdd = abs(max_drawdown(equity_curve))
    if mdd < 1e-12:
        return 0.0
    ann_return = float(np.mean(np.asarray(returns, dtype=float))) * periods_per_year
    return ann_return / mdd


def win_rate(trades: list[dict]) -> float:
    """Fraction of closed trades with strictly positive PnL."""
    closed = [t for t in trades if t.get("pnl") is not None]
    if not closed:
        return 0.0
    return sum(1 for t in closed if t["pnl"] > 0) / len(closed)


def profit_factor(trades: list[dict]) -> float:
    """Gross profit / gross loss.

    > 1.0 means more was won than lost.
    Returns 0.0 when there are no profits and no losses.
    """
    closed       = [t for t in trades if t.get("pnl") is not None]
    gross_profit = sum(t["pnl"] for t in closed if t["pnl"] > 0)
    gross_loss   = sum(abs(t["pnl"]) for t in closed if t["pnl"] < 0)
    if gross_loss < 1e-12:
        return 0.0 if gross_profit < 1e-12 else float("inf")
    return gross_profit / gross_loss


# ── Composite ─────────────────────────────────────────────────────────────────

def compute_all(
    returns: np.ndarray,
    equity_curve: np.ndarray,
    trades: list[dict],
    periods_per_year: float = 252.0,
) -> dict:
    """
    Compute the full set of performance metrics.

    Returns a dict suitable for use as ``BacktestResult.metrics``.
    """
    eq = np.asarray(equity_curve, dtype=float)
    total_return = float(eq[-1] / eq[0] - 1) if len(eq) > 1 and eq[0] > 0 else 0.0
    mdd = max_drawdown(eq)

    return {
        "total_return_pct": round(total_return * 100, 4),
        "sharpe_ratio":     round(sharpe_ratio(returns,     periods_per_year=periods_per_year), 4),
        "sortino_ratio":    round(sortino_ratio(returns,    periods_per_year=periods_per_year), 4),
        "max_drawdown_pct": round(mdd * 100,                                                   4),
        "calmar_ratio":     round(calmar_ratio(returns, eq, periods_per_year),                 4),
        "win_rate":         round(win_rate(trades),                                            4),
        "profit_factor":    round(profit_factor(trades),                                       4),
        "n_trades":         len(trades),
    }
