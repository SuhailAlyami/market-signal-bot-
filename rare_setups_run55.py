"""Run 55. Fixed before any trade result is computed.

BAA minus the 10-year was round 48. This is Moody's BAA minus Moody's
AAA, the gap between two corporate grades. Both FRED series are monthly
averages dated the first of the month, so the month is known only after
it ends. Entry is 09:30 ET on the first cash session of the next month.
Exit is 15:55 ET twenty sessions later.

A three-month change crossing from positive to negative is a long. The
opposite cross is a short. Replication is DIA.
"""
from __future__ import annotations

from datetime import date
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
from rare_setups_run54 import build_spx as build54
from rare_setups_run54 import matrix_through_53, signals_for as signals54
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("quality_compress_long", "quality_widen_short")
SIDES = {"quality_compress_long": 1, "quality_widen_short": -1}
HOLD = 20
DAILY = Path("/tmp/rare_data/daily")


def signals_for() -> dict[str, list[date]]:
    spread = (fred_series("BAA") - fred_series("AAA")).dropna().sort_index()
    change = spread.diff(3)
    compress = (change.shift(1) > 0) & (change < 0)
    widen = (change.shift(1) < 0) & (change > 0)
    return {
        "quality_compress_long": [stamp.date() for stamp in spread.index[compress.fillna(False)]],
        "quality_widen_short": [stamp.date() for stamp in spread.index[widen.fillna(False)]],
    }


def tradable_day(obs: date) -> date:
    if obs.month == 12:
        return date(obs.year + 1, 1, 1)
    return date(obs.year, obs.month + 1, 1)


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for obs in signals[name]:
            entry_day = first_session_on_or_after(state["session_dates"], max(tradable_day(obs), exit_day + __import__("datetime").timedelta(days=1)))
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


def build_dia(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "DIA")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for obs in signals[name]:
            raw = tradable_day(obs)
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
    dia = build_dia(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_53(state, usa, tech, yahoo, tradable)
    matrix.update(build54(state, signals54()))
    finish(
        lambda name: {"entry": "09:30 ET on the first session of the next month", "exit": "15:55 ET, 20 sessions later", "replication": "DIA"},
        book, dia, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run55.json"),
        "Monthly BAA minus AAA. Three-month change crossing zero. Known the following month. Not BAA minus the 10-year.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
