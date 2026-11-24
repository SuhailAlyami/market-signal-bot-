"""Run 49. Fixed before any trade result is computed.

Round 42 was the nominal 10-year yield. This is the 10-year real yield,
FRED DFII10, in percent. A rise of at least 0.10 is 10 basis points, and
a fall of at least 0.10 is the other event. Each event is traded long
and short. The print is known the next session. Entry is 09:30 ET.
Exit is 15:55 ET that same session. Replication is IWM.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import open_map
from rare_setups_run24 import fred_series
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, trade_row
from rare_setups_run47 import matrix_through_46
from rare_setups_run47 import build_spx as build47
from rare_setups_run47 import signals_for as signals47
from rare_setups_run48 import build_spx as build48
from rare_setups_run48 import signals_for as signals48
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("real_up_long", "real_up_short", "real_down_long", "real_down_short")
SIDES = {"real_up_long": 1, "real_up_short": -1, "real_down_long": 1, "real_down_short": -1}
DAILY = Path("/tmp/rare_data/daily")


def next_map(days: list[date], tradable: list[date]) -> list[date]:
    found = []
    for day in days:
        entry = next((item for item in tradable if item > day and (item - day).days <= 4), None)
        if entry is not None:
            found.append(entry)
    return found


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    series = fred_series("DFII10").dropna().sort_index()
    change = series.diff()
    up = [stamp.date() for stamp in series.index[(change >= 0.10).fillna(False)]]
    down = [stamp.date() for stamp in series.index[(change <= -0.10).fillna(False)]]
    up_entry, down_entry = next_map(up, tradable), next_map(down, tradable)
    return {
        "real_up_long": up_entry,
        "real_up_short": list(up_entry),
        "real_down_long": down_entry,
        "real_down_short": list(down_entry),
    }


def build_spx(state, entries) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        side = SIDES[name]
        seen = set()
        for day in entries[name]:
            if day in seen:
                continue
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
            seen.add(day)
    return book


def build_iwm(entries, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        seen = set()
        for day in entries[name]:
            if day not in days or day in seen:
                continue
            i = days[day]
            entry_px = float(work["open"].iloc[i])
            exit_px = float(work["close"].iloc[i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
            seen.add(day)
    return book


def main() -> None:
    print("PRE-REGISTERED", NEW_CELLS, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    signals = signals_for(tradable)
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_46(state, usa, tech, yahoo, tradable)
    matrix.update(build47(state, signals47(tradable)))
    matrix.update(build48(state, signals48()))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET the same session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run49.json"),
        "10-year TIPS yield moves at least 10 basis points. Both directions. The nominal 10-year shock is not repeated.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
