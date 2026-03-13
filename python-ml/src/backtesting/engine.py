"""
Event-driven backtesting engine.

Fill model (no look-ahead bias):
  - Signal generated at bar[i] close
  - Order executed at bar[i+1] open
  - Commission charged at both entry and exit

Long-only, single-asset.  Multi-asset support can be added in a
future sprint by running one engine instance per symbol.

Usage:
    from src.backtesting.engine import BacktestEngine
    from src.backtesting.strategies import BuyAndHoldStrategy
    from src.backtesting.data_loader import load_bars

    bars   = load_bars("AAPL", period="6m")
    result = BacktestEngine().run(BuyAndHoldStrategy(), bars)
    print(result.metrics)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .metrics import compute_all


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass
class BacktestResult:
    """Complete result of a single backtest run."""
    strategy:        str
    symbol:          str
    period_bars:     int
    initial_capital: float
    final_equity:    float
    equity_curve:    list[float]
    daily_returns:   list[float]
    trades:          list[dict]
    metrics:         dict


# ── Engine ─────────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Single-asset long-only event-driven backtester.

    Supports:
      - Long entry (BUY) and exit (SELL) signals
      - Full or partial position sizing via ``signal["size"]``
      - Configurable per-side commission
      - Look-ahead-free fills (next bar's open)
      - Final open position closed at last bar's close for trade accounting
    """

    def __init__(
        self,
        commission: float       = 0.001,   # 0.1% per side
        periods_per_year: float = 252.0,
    ) -> None:
        self.commission       = commission
        self.periods_per_year = periods_per_year

    def run(
        self,
        strategy,
        bars: list[dict],
        initial_capital: float = 100_000.0,
    ) -> BacktestResult:
        """
        Run a backtest over a list of bars.

        Args:
            strategy:        Any Strategy instance.
            bars:            List of tick dicts (oldest first).
            initial_capital: Starting cash (default $100 000).

        Returns:
            BacktestResult with equity curve, trades, and performance metrics.
        """
        if not bars:
            return self._empty_result(strategy, initial_capital)

        symbol = bars[0].get("symbol", "UNKNOWN")

        # ── Portfolio state ────────────────────────────────────────────────────
        cash             = float(initial_capital)
        qty              = 0.0    # shares held
        avg_cost         = 0.0    # entry fill price
        entry_total_cost = 0.0    # cash paid at entry (trade_value + commission)
        entry_time       = ""

        equity_curve:   list[float] = []
        trades:         list[dict]  = []
        pending_signal: dict | None = None

        for i, bar in enumerate(bars):
            close = float(bar.get("close", 0.0))

            # ── Execute pending order at this bar's open ───────────────────────
            if pending_signal is not None:
                fill_price = float(bar.get("open", close))
                action     = pending_signal.get("action", "HOLD")
                size       = min(float(pending_signal.get("size", 1.0)), 1.0)

                if action == "BUY" and qty == 0.0 and fill_price > 0:
                    # size = fraction of cash to allocate (commission-inclusive):
                    #   entry_total_cost = cash * size  (≤ cash by construction)
                    #   trade_value      = entry_total_cost / (1 + commission)
                    entry_total_cost = cash * size
                    trade_value      = entry_total_cost / (1.0 + self.commission)
                    if trade_value > 0:
                        qty      = trade_value / fill_price
                        avg_cost = fill_price
                        cash    -= entry_total_cost
                        entry_time = bar.get("timestamp", "")

                elif action == "SELL" and qty > 0.0:
                    exit_value    = qty * fill_price
                    net_proceeds  = exit_value * (1.0 - self.commission)
                    pnl           = net_proceeds - entry_total_cost
                    ret_pct       = pnl / entry_total_cost if entry_total_cost > 0 else 0.0
                    trades.append({
                        "symbol":       symbol,
                        "entry_time":   entry_time,
                        "exit_time":    bar.get("timestamp", ""),
                        "entry_price":  round(avg_cost,    4),
                        "exit_price":   round(fill_price,  4),
                        "quantity":     round(qty,         6),
                        "pnl":          round(pnl,         4),
                        "return_pct":   round(ret_pct * 100, 4),
                    })
                    cash             += net_proceeds
                    qty               = 0.0
                    avg_cost          = 0.0
                    entry_total_cost  = 0.0

                pending_signal = None

            # ── Mark-to-market equity at close ────────────────────────────────
            if close > 0:
                equity_curve.append(cash + qty * close)
            else:
                equity_curve.append(equity_curve[-1] if equity_curve else initial_capital)

            # ── Generate signal for next bar (no look-ahead) ──────────────────
            try:
                signal = strategy.on_bar(bar, {})
            except Exception:
                signal = {"action": "HOLD", "size": 0.0}

            if signal.get("action") in ("BUY", "SELL"):
                pending_signal = signal

        # ── Close open position at last bar's close for trade accounting ──────
        if qty > 0.0 and bars:
            last_close   = float(bars[-1].get("close", avg_cost))
            exit_value   = qty * last_close
            net_proceeds = exit_value * (1.0 - self.commission)
            pnl          = net_proceeds - entry_total_cost
            ret_pct      = pnl / entry_total_cost if entry_total_cost > 0 else 0.0
            trades.append({
                "symbol":       symbol,
                "entry_time":   entry_time,
                "exit_time":    bars[-1].get("timestamp", ""),
                "entry_price":  round(avg_cost,   4),
                "exit_price":   round(last_close, 4),
                "quantity":     round(qty,        6),
                "pnl":          round(pnl,        4),
                "return_pct":   round(ret_pct * 100, 4),
            })
            # equity_curve[-1] = cash + qty * last_close is already correct;
            # we only record the trade here — no equity adjustment needed.

        # ── Compute metrics ────────────────────────────────────────────────────
        eq_arr  = np.asarray(equity_curve, dtype=float)
        ret_arr = (
            np.diff(eq_arr) / np.where(eq_arr[:-1] > 0, eq_arr[:-1], 1.0)
            if len(eq_arr) > 1 else np.array([])
        )
        metrics = compute_all(
            returns=ret_arr,
            equity_curve=eq_arr,
            trades=trades,
            periods_per_year=self.periods_per_year,
        )

        return BacktestResult(
            strategy        = strategy.name(),
            symbol          = symbol,
            period_bars     = len(bars),
            initial_capital = initial_capital,
            final_equity    = round(float(eq_arr[-1]) if len(eq_arr) else initial_capital, 2),
            equity_curve    = [round(float(v), 2) for v in equity_curve],
            daily_returns   = [round(float(r), 6) for r in ret_arr],
            trades          = trades,
            metrics         = metrics,
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _empty_result(self, strategy, initial_capital: float) -> BacktestResult:
        empty_metrics = compute_all(np.array([]), np.array([initial_capital]), [])
        return BacktestResult(
            strategy        = strategy.name(),
            symbol          = "UNKNOWN",
            period_bars     = 0,
            initial_capital = initial_capital,
            final_equity    = initial_capital,
            equity_curve    = [],
            daily_returns   = [],
            trades          = [],
            metrics         = empty_metrics,
        )
