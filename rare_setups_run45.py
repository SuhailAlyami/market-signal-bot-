"""Run 45. Fixed before any trade result is computed.

NFCI was round 24. This is the St. Louis Fed Financial Stress Index,
STLFSI4. The observation date is the Friday. The index is public the
following Thursday, so the entry is the first cash session on or after
six days later, at 09:30 ET. Exit is 15:55 ET ten sessions later.

The four-week change crossing from positive to negative is a long.
The cross from negative to positive is a short. One position per rule.
Replication is IWM.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import first_session_on_or_after, open_map
from rare_setups_run24 import fred_series
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, trade_row
from rare_setups_run41 import later_matrix
from rare_setups_run41 import build_spx as build41
from rare_setups_run41 import signals_for as signals41
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("stlfsi_ease_long", "stlfsi_tighten_short")
SIDES = {"stlfsi_ease_long": 1, "stlfsi_tighten_short": -1}
HOLD = 10
DAILY = Path("/tmp/rare_data/daily")


def signals_for() -> dict[str, list[date]]:
    series = fred_series("STLFSI4").dropna().sort_index()
    change = series - series.shift(4)
    ease = (change.shift(1) > 0) & (change < 0)
    tighten = (change.shift(1) < 0) & (change > 0)
    return {
        "stlfsi_ease_long": [stamp.date() for stamp in series.index[ease.fillna(False)]],
        "stlfsi_tighten_short": [stamp.date() for stamp in series.index[tighten.fillna(False)]],
    }


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for obs in signals[name]:
            raw = obs + timedelta(days=6)
            entry_day = first_session_on_or_after(state["session_dates"], raw)
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
        for obs in signals[name]:
            raw = obs + timedelta(days=6)
            entry_i = next((i for i, day in enumerate(days) if day >= raw and day > exit_day), None)
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
    from rare_setups_run41 import later_matrix, signals_for as nhnl_signals, build_spx as nhnl_book
    matrix = later_matrix(state, usa, tech, yahoo, tradable)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(nhnl_book(state, nhnl_signals(panel)))
    finish(
        lambda name: {"entry": "09:30 ET on the Thursday after the Friday observation", "exit": "15:55 ET, 10 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run45.json"),
        "STLFSI4 four-week change crossing zero. Known the following Thursday. NFCI is not repeated.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
