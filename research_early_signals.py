"""Compare early-warning hypotheses on completed ES/NQ one-minute bars.

Research only: no live orders, no option-price claims. Strict forward outcomes.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
import yfinance as yf


def candidates(data: pd.DataFrame, i: int):
    """All decisions use current and earlier completed candles only."""
    if i < 21:
        return {}
    prev = data.iloc[i-20:i]
    last = data.iloc[i]
    if prev[["High", "Low", "Close", "Volume"]].isna().any().any():
        return {}
    if (prev.Volume <= 0).any() or last.Volume <= 0:
        return {}
    close = float(last.Close)
    high = float(prev.High.max())
    low = float(prev.Low.min())
    span = max(high-low, 1e-9)
    volume = float(last.Volume / prev.Volume.median())
    move = float(last.Close-last.Open)
    typical = float((prev.High-prev.Low).median())
    if typical <= 0:
        return {}
    # 1. Pre-breakout: price compresses near the edge before crossing.
    narrow = float((data.High.iloc[i-4:i].max()-data.Low.iloc[i-4:i].min()) / span) < 0.42
    pre_up = narrow and high-close >= 0 and (high-close)/span < 0.12 and move > 0
    pre_down = narrow and close-low >= 0 and (close-low)/span < 0.12 and move < 0
    # 2. First-minute momentum: not dependent on a completed 5m bar.
    impulse_up = move > 1.6*typical and volume >= 1.3 and close > float(last.Open)
    impulse_down = -move > 1.6*typical and volume >= 1.3 and close < float(last.Open)
    # 3. First breakout with relative volume.
    break_up = close > high and volume >= 1.3
    break_down = close < low and volume >= 1.3
    return {"pre_level": 1 if pre_up else -1 if pre_down else 0,
            "impulse": 1 if impulse_up else -1 if impulse_down else 0,
            "breakout": 1 if break_up else -1 if break_down else 0}


def evaluate(data: pd.DataFrame, horizon=5):
    data = data.sort_index()
    if data.index.tz is None:
        raise ValueError("Timezone-aware bars required")
    if horizon < 1:
        raise ValueError("Positive horizon required")
    results = {name: [] for name in ("pre_level", "impulse", "breakout")}
    opportunities = 0
    for i in range(21, len(data)-horizon):
        # Do not score gaps, weekends or overnight discontinuities.
        window = data.index[i-20:i+horizon+1]
        if not (window.to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all():
            continue
        entry = float(data.Close.iloc[i])
        future = data.iloc[i+1:i+horizon+1]
        if entry <= 0:
            continue
        swing = max(abs(float(future.High.max())/entry-1),abs(float(future.Low.min())/entry-1))
        opportunities += int(swing >= 0.001)
        for name, direction in candidates(data,i).items():
            if not direction:
                continue
            signed = direction*(float(future.Close.iloc[-1])/entry-1)*100
            results[name].append(round(signed,5))
    return {"horizon_minutes":horizon,"large_move_windows_0_1pct":opportunities,
            "methods":{name:{"signals":len(v),"directional_hit_rate":round(sum(x>0 for x in v)/len(v),4) if v else None,
                              "mean_forward_move_pct":round(sum(v)/len(v),5) if v else None}
                       for name,v in results.items()},
            "limitations":["Yahoo minute history may be delayed and is short.",
                           "Signals use completed 1-minute candles, not tick-level prediction.",
                           "Overlapping samples are correlated; no option bid/ask or transaction costs.",
                           "This is exploratory, not an out-of-sample or profitable strategy claim."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbol",choices=["ES=F","NQ=F"],default="ES=F")
    p.add_argument("--period",choices=["1d","5d","7d"],default="5d")
    p.add_argument("--output",default="early_research_results.json")
    a=p.parse_args()
    bars=yf.Ticker(a.symbol).history(period=a.period,interval="1m",auto_adjust=True)
    if bars.empty:
        raise SystemExit("No one-minute data; no result fabricated")
    result={"symbol":a.symbol,**evaluate(bars)}
    Path(a.output).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
