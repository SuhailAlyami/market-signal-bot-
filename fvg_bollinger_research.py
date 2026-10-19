"""Causal, research-only FVG + Bollinger breakout detector.

All features at bar i use bars <= i. Signals only on completed candles.
This is a breakout *confirmation*, not a pre-breakout prediction or option quote.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import mean, pstdev

@dataclass(frozen=True)
class Signal:
    index: int
    direction: str
    fvg: bool
    volume_ratio: float
    close: float
    upper_band: float
    lower_band: float
    research_only: bool = True


def detect(bars: list[dict], *, length: int = 20,
           bb_mult: float = 2.0, volume_mult: float = 1.5,
           require_fvg: bool = False) -> list[Signal]:
    """Bars must be chronological completed OHLCV dictionaries.

    A volume baseline uses PREVIOUS candles, excluding the breakout candle.
    An FVG is confirmed only when the current candle closes.
    """
    if length < 3 or not isfinite(bb_mult) or bb_mult <= 0 or not isfinite(volume_mult) or volume_mult <= 0:
        raise ValueError("Invalid detector parameters")
    result = []
    for i in range(length + 1, len(bars)):
        window = bars[i-length:i]
        prior = bars[i-length-1:i-1]
        curr = bars[i]
        needed = [*(b[k] for b in window for k in ("close", "volume")),
                  *(b["close"] for b in prior), *(curr[k] for k in ("open", "high", "low", "close", "volume")),
                  bars[i-2]["high"], bars[i-2]["low"], bars[i-1]["close"]]
        if not all(isinstance(v, (int, float)) and isfinite(v) for v in needed):
            continue
        if any(b["volume"] <= 0 or b["close"] <= 0 for b in window) or curr["volume"] <= 0:
            continue
        # Current BB uses the last length closes, like ta.sma/ta.stdev at bar i.
        closes = [b["close"] for b in bars[i-length+1:i+1]]
        previous_closes = [b["close"] for b in bars[i-length:i]]
        basis = mean(closes)
        previous_basis = mean(previous_closes)
        upper = basis + bb_mult * pstdev(closes)
        lower = basis - bb_mult * pstdev(closes)
        previous_upper = previous_basis + bb_mult * pstdev(previous_closes)
        previous_lower = previous_basis - bb_mult * pstdev(previous_closes)
        avg_volume = mean(b["volume"] for b in window)
        if avg_volume <= 0 or curr["volume"] <= volume_mult * avg_volume:
            continue
        bullish_fvg = curr["low"] > bars[i-2]["high"] and bars[i-1]["close"] > bars[i-2]["high"]
        bearish_fvg = curr["high"] < bars[i-2]["low"] and bars[i-1]["close"] < bars[i-2]["low"]
        bullish = curr["close"] > upper and bars[i-1]["close"] <= previous_upper
        bearish = curr["close"] < lower and bars[i-1]["close"] >= previous_lower
        if bullish and (bullish_fvg or not require_fvg):
            direction = "UP"
            fvg = bullish_fvg
        elif bearish and (bearish_fvg or not require_fvg):
            direction = "DOWN"
            fvg = bearish_fvg
        else:
            continue
        result.append(Signal(i, direction, fvg, round(curr["volume"] / avg_volume, 3),
                             curr["close"], round(upper, 4), round(lower, 4)))
    return result
