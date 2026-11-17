"""Run 36. Fixed before any trade result is computed.

FOMC and CPI were entered at 18:00 on the release day. NFP was the whole
week of the first Friday. This round is only the next cash session:
09:30 ET to 15:55 ET the day after the release. FOMC uses the decision
date. CPI uses the published release date. NFP is the first Friday.
Long and short are both rules, so the sign is not chosen afterward.
Replication is QQQ.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run16 import CPI
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import open_map
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, trade_row
from rare_setups_run34 import build_spx as build34
from rare_setups_run34 import matrix_through_33
from rare_setups_run34 import signals_for as signals34
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_study import FOMC, build_daily

NEW_CELLS = (
    "fomc_nextday_long",
    "fomc_nextday_short",
    "cpi_nextday_long",
    "cpi_nextday_short",
    "nfp_nextday_long",
    "nfp_nextday_short",
)
SIDES = {name: (1 if name.endswith("long") else -1) for name in NEW_CELLS}


def first_fridays(days: list[date]) -> list[date]:
    seen = set()
    found = []
    for day in days:
        key = (day.year, day.month)
        if day.weekday() == 4 and day.day <= 7 and key not in seen:
            seen.add(key)
            found.append(day)
    return found


def next_sessions(days: list[date], events: list[date]) -> list[date]:
    found = []
    for event in events:
        entry = next((day for day in days if day > event), None)
        if entry is not None and (entry - event).days <= 5:
            found.append(entry)
    return sorted(set(found))


def signals_for(days: list[date]) -> dict[str, list[date]]:
    events = {
        "fomc": sorted(day for day in FOMC if day <= days[-1]),
        "cpi": sorted(day for day in CPI if day <= days[-1]),
        "nfp": first_fridays(days),
    }
    book = {}
    for stem, dates in events.items():
        entries = next_sessions(days, dates)
        book[f"{stem}_nextday_long"] = entries
        book[f"{stem}_nextday_short"] = list(entries)
    return book


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        side = SIDES[name]
        for day in signals[name]:
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
    return book


def build_qqq(signals, last_day: date) -> dict[str, list[dict]]:
    frame = __import__("rare_setups_study", fromlist=["load_daily"]).load_daily(Path("/tmp/rare_data/daily"), "QQQ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        for day in signals[name]:
            if day not in days or day > last_day:
                continue
            i = days[day]
            entry_px = float(work["open"].iloc[i])
            exit_px = float(work["close"].iloc[i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
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
    qqq = build_qqq(signals, last_day)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    finish(
        lambda name: {"entry": "09:30 ET the session after the release", "exit": "15:55 ET the same session", "replication": "QQQ"},
        book, qqq, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run36.json"),
        "Next cash session after FOMC, CPI, or the first Friday. 09:30 to 15:55. Both directions.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
