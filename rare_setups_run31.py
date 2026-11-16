"""Run 31. Fixed before any trade result is computed.

Turn-of-month enters at the month-end reopen and holds into the new
month. This round is the quarter-end window itself: the last two cash
sessions of March, June, September, and December. Entry is 09:30 ET on
the second-to-last session. Exit is 15:55 ET on the last session. Long
and short are both rules. Replication is IWM.
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
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import base_matrix, build_spx as build28, finish, signals_for as signals28, trade_row
from rare_setups_run29 import build_spx as build29
from rare_setups_run29 import signals_for as signals29
from rare_setups_run30 import build_spx as build30
from rare_setups_run30 import signals_for as signals30
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("quarter_end_long", "quarter_end_short")
SIDES = {"quarter_end_long": 1, "quarter_end_short": -1}
DAILY = Path("/tmp/rare_data/daily")


def spans(days: list[date]) -> list[tuple[date, date]]:
    found = []
    for i, day in enumerate(days):
        if i == 0:
            continue
        month_end = i + 1 == len(days) or days[i + 1].month != day.month
        if month_end and day.month in (3, 6, 9, 12):
            found.append((days[i - 1], day))
    return found


def signals_for(days: list[date]) -> dict[str, list[date]]:
    entries = [entry for entry, _exit in spans(days)]
    return {"quarter_end_long": entries, "quarter_end_short": list(entries)}


def build_spx(state, days: list[date]) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for entry_day, exit_day in spans(days):
        entry_i = opens.get(entry_day)
        exit_i = state["close_i"].get(exit_day)
        if entry_i is None or exit_i is None or exit_i <= entry_i:
            continue
        entry_px = float(state["open"][entry_i])
        exit_px = float(state["close"][exit_i])
        for name, side in SIDES.items():
            book[name].append(trade_row(entry_day, side * (exit_px - entry_px), entry_px, side))
    return book


def build_iwm(days: list[date], last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    idays = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for entry_day, exit_day in spans(idays):
        entry_px = float(work.loc[work.index.date == entry_day, "open"].iloc[0])
        exit_px = float(work.loc[work.index.date == exit_day, "close"].iloc[0])
        if entry_px <= 0:
            continue
        for name, side in SIDES.items():
            book[name].append(trade_row(entry_day, side * (exit_px - entry_px) / entry_px, entry_px, side))
    return book


def main() -> None:
    print("PRE-REGISTERED", NEW_CELLS, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    book = build_spx(state, tradable)
    for name in NEW_CELLS:
        print(" signals", name, len(book[name]), flush=True)
    iwm = build_iwm(tradable, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    matrix.update(build29(state, signals29(state, set(tradable))))
    matrix.update(build30(state, signals30(tradable)))
    finish(
        lambda name: {"entry": "09:30 ET on the second-to-last quarter session", "exit": "15:55 ET on the last quarter session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run31.json"),
        "Last two cash sessions of March, June, September, and December. Not the turn-of-month hold into the next month.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
