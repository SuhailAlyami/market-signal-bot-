"""Run 37. Fixed before any trade result is computed.

HYG/LQD reclaim and NFCI rollover were round 24. The ICE high-yield
option-adjusted spread was stored and not traded, because the file
starts on 13 November 2023. This round trades that series anyway and
does not stretch it backward.

The 5-day change in the spread is known on its observation date. A
cross from positive to negative is a long. A cross from negative to
positive is a short. Entry is the next session at 09:30 ET. Exit is
15:55 ET five sessions later. Replication is IWM.
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
from rare_setups_run24 import fred_series
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, trade_row
from rare_setups_run34 import build_spx as build34
from rare_setups_run34 import matrix_through_33
from rare_setups_run34 import signals_for as signals34
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_run36 import build_spx as build36
from rare_setups_run36 import signals_for as signals36
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("oas_compress_long", "oas_widen_short")
SIDES = {"oas_compress_long": 1, "oas_widen_short": -1}
HOLD = 5
DAILY = Path("/tmp/rare_data/daily")


def signals_for() -> dict[str, list[date]]:
    oas = fred_series("BAMLH0A0HYM2").dropna().sort_index()
    change = oas.diff(5)
    compress = (change.shift(1) > 0) & (change < 0)
    widen = (change.shift(1) < 0) & (change > 0)
    return {
        "oas_compress_long": [stamp.date() for stamp in oas.index[compress.fillna(False)]],
        "oas_widen_short": [stamp.date() for stamp in oas.index[widen.fillna(False)]],
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
    signals = signals_for()
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    matrix.update(build36(state, signals36(tradable)))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 5 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run37.json"),
        "ICE HY OAS from 2023-11-13. Five-day change crossing zero. Next 09:30, exit after 5 sessions.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
