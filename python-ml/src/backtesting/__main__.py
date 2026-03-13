"""
CLI entry-point for the backtesting engine.

Usage:
    python -m src.backtesting --symbol AAPL --period 6m --capital 100000
    python -m src.backtesting --symbol MSFT --strategy nexquant --period 1y
"""

from __future__ import annotations

import argparse
import json
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.backtesting",
        description="NexQuant Backtesting Engine — Sprint 1.4",
    )
    p.add_argument("--symbol",   default="AAPL",       help="Ticker symbol (default: AAPL)")
    p.add_argument("--exchange", default="US",         help="Exchange label (default: US)")
    p.add_argument("--period",   default="6m",
                   choices=["1m", "3m", "6m", "1y", "2y"],
                   help="Historical period (default: 6m)")
    p.add_argument("--interval", default="1d",         help="Bar interval (default: 1d)")
    p.add_argument("--capital",  default=100_000.0,    type=float,
                   help="Initial capital (default: 100000)")
    p.add_argument("--commission", default=0.001,      type=float,
                   help="Per-side commission fraction (default: 0.001 = 0.1%%)")
    p.add_argument("--strategy", default="buyandhold",
                   choices=["buyandhold", "random", "nexquant"],
                   help="Strategy to run (default: buyandhold)")
    p.add_argument("--json",     action="store_true",  help="Output metrics as JSON")
    return p


def _make_strategy(name: str):
    from src.backtesting.strategies import (
        BuyAndHoldStrategy, RandomStrategy, NexQuantStrategy
    )
    if name == "buyandhold":
        return BuyAndHoldStrategy()
    if name == "random":
        return RandomStrategy()
    return NexQuantStrategy()


def main() -> None:
    args    = _build_parser().parse_args()

    from src.backtesting.data_loader import load_bars
    from src.backtesting.engine import BacktestEngine

    print(f"Loading {args.period} of {args.interval} bars for {args.symbol}…")
    bars = load_bars(args.symbol, period=args.period,
                     exchange=args.exchange, interval=args.interval)
    print(f"  {len(bars)} bars loaded")

    strategy = _make_strategy(args.strategy)
    engine   = BacktestEngine(commission=args.commission)

    print(f"Running {strategy.name()} backtest…")
    result   = engine.run(strategy, bars, initial_capital=args.capital)

    if args.json:
        # Strip equity_curve for cleaner output
        out = {
            "strategy":        result.strategy,
            "symbol":          result.symbol,
            "period_bars":     result.period_bars,
            "initial_capital": result.initial_capital,
            "final_equity":    result.final_equity,
            "metrics":         result.metrics,
            "n_trades":        len(result.trades),
        }
        print(json.dumps(out, indent=2))
        return

    m = result.metrics
    gate = "✅ PASS" if m["sharpe_ratio"] >= 1.0 else "❌ FAIL"
    print()
    print(f"{'─'*50}")
    print(f"  Strategy     : {result.strategy}")
    print(f"  Symbol       : {result.symbol}")
    print(f"  Bars         : {result.period_bars}")
    print(f"  Capital      : ${result.initial_capital:,.0f}  →  ${result.final_equity:,.2f}")
    print(f"  Total return : {m['total_return_pct']:+.2f}%")
    print(f"{'─'*50}")
    print(f"  Sharpe       : {m['sharpe_ratio']:.3f}   {gate}")
    print(f"  Sortino      : {m['sortino_ratio']:.3f}")
    print(f"  Max Drawdown : {m['max_drawdown_pct']:.2f}%")
    print(f"  Calmar       : {m['calmar_ratio']:.3f}")
    print(f"  Win rate     : {m['win_rate']*100:.1f}%")
    print(f"  Profit factor: {m['profit_factor']:.3f}")
    print(f"  Trades       : {m['n_trades']}")
    print(f"{'─'*50}")

    sys.exit(0 if m["sharpe_ratio"] >= 1.0 else 1)


if __name__ == "__main__":
    main()
