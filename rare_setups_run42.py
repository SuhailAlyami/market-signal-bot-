"""Run 42. Fixed before any trade result is computed.

The curve uninversion was one level event. MOVE was the volatility of
yields. This is a one-day jump in the 10-year yield itself. Yahoo ^TNX
is the yield in percent, so 0.10 is 10 basis points.

A rise of at least 10bp and a fall of at least 10bp are both events.
Each event is traded long and short, so the sign is not chosen later.
The yield is known at the cash close. Entry is the next session at
09:30 ET. Exit is 15:55 ET that same session. Replication is IWM.
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
from rare_setups_run28 import finish, trade_row
from rare_setups_run41 import build_spx as build41
from rare_setups_run41 import later_matrix, signals_for as signals41
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("tnx_up_long", "tnx_up_short", "tnx_down_long", "tnx_down_short")
SIDES = {
    "tnx_up_long": 1,
    "tnx_up_short": -1,
    "tnx_down_long": 1,
    "tnx_down_short": -1,
}
DAILY = Path("/tmp/rare_data/daily")


def signal_days() -> dict[str, list[date]]:
    frame = load_daily(DAILY, "TNX")
    change = frame["Close"].diff()
    up = [stamp.date() for stamp in change.index[(change >= 0.10).fillna(False)]]
    down = [stamp.date() for stamp in change.index[(change <= -0.10).fillna(False)]]
    return {"up": up, "down": down}


def next_entries(raw: dict[str, list[date]], tradable: list[date]) -> dict[str, list[date]]:
    def nxt(days):
        found = []
        for day in days:
            entry = next((item for item in tradable if item > day and (item - day).days <= 4), None)
            if entry is not None:
                found.append(entry)
        return found
    up, down = nxt(raw["up"]), nxt(raw["down"])
    return {
        "tnx_up_long": up,
        "tnx_up_short": list(up),
        "tnx_down_long": down,
        "tnx_down_short": list(down),
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
    entries = next_entries(signal_days(), tradable)
    for name in NEW_CELLS:
        print(" signals", name, len(entries[name]), flush=True)
    book = build_spx(state, entries)
    iwm = build_iwm(entries, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = later_matrix(state, usa, tech, yahoo, tradable)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build41(state, signals41(panel)))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET the same session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run42.json"),
        "10-year yield move of at least 10 basis points. Both directions. Dollar shocks and the curve uninversion were already tested.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
