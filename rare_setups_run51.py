"""Run 51. Fixed before any trade result is computed.

The 10-year minus 2-year uninversion was a level event: twenty negative
days, then a non-negative print. This is a different event. The 20-day
change in the spread crosses through zero. Two spreads are included,
10-year minus 3-month and 10-year minus 2-year. A cross from negative
to positive is a steepening long. The opposite cross is a flattening
short. Entry is the next session at 09:30 ET. Exit is 15:55 ET ten
sessions later. Replication is DIA.
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
from rare_setups_run47 import matrix_through_46
from rare_setups_run47 import build_spx as build47
from rare_setups_run47 import signals_for as signals47
from rare_setups_run48 import build_spx as build48
from rare_setups_run48 import signals_for as signals48
from rare_setups_run49 import build_spx as build49
from rare_setups_run49 import signals_for as signals49
from rare_setups_study import build_daily, load_daily

NEW_CELLS = (
    "t10y3m_steepen_long",
    "t10y3m_flatten_short",
    "t10y2y_steepen_long",
    "t10y2y_flatten_short",
)
SIDES = {
    "t10y3m_steepen_long": 1,
    "t10y3m_flatten_short": -1,
    "t10y2y_steepen_long": 1,
    "t10y2y_flatten_short": -1,
}
HOLD = 10
DAILY = Path("/tmp/rare_data/daily")
TREASURY = Path("/tmp/rare_data/external/treasury")


def spreads() -> pd.DataFrame:
    frames = []
    for path in sorted(TREASURY.glob("*.csv")):
        frame = pd.read_csv(path)
        if "10 Yr" not in frame.columns or "3 Mo" not in frame.columns or "2 Yr" not in frame.columns:
            continue
        frame["Date"] = pd.to_datetime(frame["Date"], format="%m/%d/%Y")
        frames.append(frame[["Date", "10 Yr", "3 Mo", "2 Yr"]])
    all_rows = pd.concat(frames, ignore_index=True)
    for column in ("10 Yr", "3 Mo", "2 Yr"):
        all_rows[column] = pd.to_numeric(all_rows[column], errors="coerce")
    all_rows = all_rows.dropna().drop_duplicates("Date", keep="last").sort_values("Date")
    all_rows = all_rows.set_index("Date")
    return pd.DataFrame({
        "t10y3m": all_rows["10 Yr"] - all_rows["3 Mo"],
        "t10y2y": all_rows["10 Yr"] - all_rows["2 Yr"],
    })


def signals_for() -> dict[str, list[date]]:
    book = spreads()
    found = {name: [] for name in NEW_CELLS}
    for stem, column in (("t10y3m", "t10y3m"), ("t10y2y", "t10y2y")):
        change = book[column].diff(20)
        steep = (change.shift(1) < 0) & (change > 0)
        flat = (change.shift(1) > 0) & (change < 0)
        found[f"{stem}_steepen_long"] = [stamp.date() for stamp in book.index[steep.fillna(False)]]
        found[f"{stem}_flatten_short"] = [stamp.date() for stamp in book.index[flat.fillna(False)]]
    return found


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
    dia = build_dia(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_46(state, usa, tech, yahoo, tradable)
    matrix.update(build47(state, signals47(tradable)))
    matrix.update(build48(state, signals48()))
    matrix.update(build49(state, signals49(tradable)))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 10 sessions later", "replication": "DIA"},
        book, dia, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run51.json"),
        "20-day change in 10y-3m and 10y-2y crossing zero. Not the old uninversion level rule.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
