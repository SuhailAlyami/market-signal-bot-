"""Run 43. Fixed before any trade result is computed.

Zweig and the 90/90 day use the advance share as a thrust. This is a
disagreement. The S&P close is a 20-day high while the 10-day sum of
member advances minus declines is negative, or a 20-day low while that
sum is positive. The member tape and the index close are known together.
Entry is the next session at 09:30 ET. Exit is 15:55 ET five sessions
later. The high is a short. The low is a long. Replication is IWM.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import next_session_after, open_map
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, trade_row
from rare_setups_run41 import later_matrix
from rare_setups_run41 import build_spx as build41
from rare_setups_run41 import signals_for as signals41
from rare_setups_run42 import build_spx as build42
from rare_setups_run42 import next_entries, signal_days
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("ad_bull_long", "ad_bear_short")
SIDES = {"ad_bull_long": 1, "ad_bear_short": -1}
HOLD = 5
DAILY = Path("/tmp/rare_data/daily")


def signals_for(panel: pd.DataFrame) -> dict[str, list[date]]:
    close = panel.sort_index()
    both = close.notna() & close.shift(1).notna()
    advances = ((close > close.shift(1)) & both).sum(axis=1)
    declines = ((close < close.shift(1)) & both).sum(axis=1)
    present = both.sum(axis=1)
    net10 = (advances - declines).rolling(10).sum()
    gspc = load_daily(DAILY, "GSPC")["Close"].sort_index()
    gspc = gspc[~gspc.index.duplicated(keep="last")]
    high = gspc.shift(1).rolling(20).max()
    low = gspc.shift(1).rolling(20).min()
    joined = pd.concat({"px": gspc, "high": high, "low": low, "net": net10, "names": present}, axis=1).dropna()
    enough = joined["names"] >= 400
    bull = enough & (joined["px"] <= joined["low"]) & (joined["net"] > 0)
    bear = enough & (joined["px"] >= joined["high"]) & (joined["net"] < 0)
    return {
        "ad_bull_long": [stamp.date() for stamp in joined.index[bull]],
        "ad_bear_short": [stamp.date() for stamp in joined.index[bear]],
    }


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for signal_day in signals[name]:
            entry_day = next_session_after(state["session_dates"], max(signal_day, exit_day))
            if entry_day is None or entry_day <= exit_day:
                continue
            pos = state["pos"].get(entry_day)
            entry_i = opens.get(entry_day)
            if pos is None or entry_i is None or pos + HOLD >= len(state["session_dates"]):
                continue
            exit_day = state["session_dates"][pos + HOLD]
            exit_i = state["close_i"].get(exit_day)
            if exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(entry_day, side * (exit_px - entry_px), entry_px, side))
    return book


def build_iwm(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for signal_day in signals[name]:
            entry_i = next((i for i, day in enumerate(days) if day > max(signal_day, exit_day)), None)
            if entry_i is None or entry_i + HOLD >= len(days):
                continue
            exit_i = entry_i + HOLD
            entry_px = float(work["open"].iloc[entry_i])
            exit_px = float(work["close"].iloc[exit_i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(days[entry_i], side * (exit_px - entry_px) / entry_px, entry_px, side))
            exit_day = days[exit_i]
    return book


def main() -> None:
    print("PRE-REGISTERED", NEW_CELLS, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    signals = signals_for(panel)
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = later_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build41(state, signals41(panel)))
    matrix.update(build42(state, next_entries(signal_days(), tradable)))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 5 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run43.json"),
        "20-day S&P extreme disagreed with by the 10-day member advance-decline sum. FOMC, CPI, NFP, SKEW, COT, and HY OAS were already tested.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
