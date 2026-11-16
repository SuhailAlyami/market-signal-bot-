"""Run 32. Fixed before any trade result is computed.

Intraday relative volume was a breakout filter in the explosion studies.
This is the next-session fade of a daily SPY volume spike. Volume is at
least twice the average of the prior 20 sessions, not including today.
A day that closes below its open is bought at the next 09:30 ET and
sold at 15:55 ET. A day that closes above its open is sold at the next
09:30 and covered at 15:55. Replication is QQQ.
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
from rare_setups_run31 import build_spx as build31
from rare_setups_run31 import signals_for as signals31
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("volume_down_fade_long", "volume_up_fade_short")
SIDES = {"volume_down_fade_long": 1, "volume_up_fade_short": -1}
DAILY = Path("/tmp/rare_data/daily")


def signal_days() -> dict[str, list[date]]:
    frame = load_daily(DAILY, "SPY")
    volume = frame["Volume"].astype(float)
    average = volume.shift(1).rolling(20).mean()
    spike = (volume / average >= 2).fillna(False)
    down = (frame["Close"] < frame["Open"]).fillna(False)
    up = (frame["Close"] > frame["Open"]).fillna(False)
    return {
        "volume_down_fade_long": [stamp.date() for stamp in frame.index[spike & down]],
        "volume_up_fade_short": [stamp.date() for stamp in frame.index[spike & up]],
    }


def next_entries(signals, tradable: list[date]) -> dict[str, list[date]]:
    book = {}
    for name, days in signals.items():
        entries = []
        for day in days:
            entry = next((item for item in tradable if item > day), None)
            if entry is not None and (entry - day).days <= 4:
                entries.append(entry)
        book[name] = entries
    return book


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


def build_qqq(entries, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "QQQ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        seen = set()
        for day in entries[name]:
            if day not in days or day in seen or day > last_day:
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
    raw = signal_days()
    entries = next_entries(raw, tradable)
    for name in NEW_CELLS:
        print(" signals", name, len(entries[name]), flush=True)
    book = build_spx(state, entries)
    qqq = build_qqq(entries, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    matrix.update(build29(state, signals29(state, set(tradable))))
    matrix.update(build30(state, signals30(tradable)))
    matrix.update(build31(state, tradable))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET the same session", "replication": "QQQ"},
        book, qqq, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run32.json"),
        "SPY volume at least twice the prior 20-session average. Fade the day's direction at the next open. Flat at 15:55.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
