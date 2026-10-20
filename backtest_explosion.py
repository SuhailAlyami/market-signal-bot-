"""Reproducible *research-only* walk-forward signal study.

A signal at time t sees bars through t only. Outcomes use bars t+1...t+horizon.
No claim of option profitability, statistical significance, or live data latency.
"""
from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

import pandas as pd
import ibkr_market_data as market_data

from explosion_detector import assess_bars, market_session_open


def study(symbol: str, bars: pd.DataFrame, horizon: int = 6) -> dict:
    """Backtest the exact online detection logic without using future bars to decide."""
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("data must have timezone-aware bar start times")
    data = bars.sort_index()
    required = ("Open", "High", "Low", "Close", "Volume")
    if any(c not in data for c in required):
        raise ValueError("missing OHLCV columns")
    signals = []
    evaluated = 0
    for i in range(32, len(data) - horizon):
        bar_close = data.index[i] + timedelta(minutes=5)
        if not market_session_open(bar_close.to_pydatetime()):
            continue
        evaluated += 1
        # Include only the completed signal candle; future prices are hidden.
        prefix = data.iloc[:i + 1]
        now = bar_close.to_pydatetime() + timedelta(seconds=30)
        signal = assess_bars(symbol, prefix, now=now)
        if not signal:
            continue
        future = data.iloc[i + 1:i + 1 + horizon]
        # Prevent crossing a session boundary: 5-minute contiguous bars only.
        if any((future.index[j] - data.index[i if j == 0 else i+j]) > timedelta(minutes=5)
               for j in range(len(future))):
            continue
        entry = float(data["Close"].iloc[i])
        exit_price = float(future["Close"].iloc[-1])
        signed_pct = (exit_price / entry - 1) * 100
        if signal["direction"] == "BEARISH":
            signed_pct = -signed_pct
        signals.append({
            "bar_time": signal["bar_time"],
            "direction": signal["direction"],
            "score": signal["score"],
            "rvol": round(signal["rvol"], 3),
            "entry_underlying": round(entry, 4),
            "exit_underlying": round(exit_price, 4),
            "signed_underlying_move_pct": round(signed_pct, 4),
        })
    wins = sum(x["signed_underlying_move_pct"] > 0 for x in signals)
    return {
        "symbol": symbol,
        "timeframe": "5m",
        "horizon_bars": horizon,
        "bars_evaluated": evaluated,
        "signals": len(signals),
        "positive_direction_rate": round(wins / len(signals), 4) if signals else None,
        "mean_signed_underlying_move_pct": round(
            sum(x["signed_underlying_move_pct"] for x in signals) / len(signals), 4
        ) if signals else None,
        "notes": [
            "Research metric on underlying, NOT an option contract return or tradable fill.",
            "IBKR historical bars are bounded and may be revised; no realtime execution is inferred.",
            "Exploratory in-sample metric; no out-of-sample claim.",
            "Overlapping horizons/correlated signals inflate apparent sample size.",
            "Does not include spreads, option premium decay, commissions or slippage.",
        ],
        "sample": signals[:25],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="No-orders historical signal study")
    parser.add_argument("--symbol", choices=["SPY", "QQQ"], default="SPY")
    parser.add_argument("--period", default="1mo", choices=["5d", "1mo"])
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--output", default="backtest_results.json")
    args = parser.parse_args()
    bars = market_data.Ticker(args.symbol).history(
        period=args.period, interval="5m", auto_adjust=False, require_realtime=False
    )
    if bars.empty:
        raise SystemExit("No market data: no result produced")
    outcome = study(args.symbol, bars, args.horizon)
    Path(args.output).write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in outcome.items() if k != "sample"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

