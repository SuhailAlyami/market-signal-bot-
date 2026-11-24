"""Run 33. Fixed before any trade result is computed.

The yield-curve uninversion was one event in round 20. This is the
10-year note auction calendar. The date is the competitive close, which
is about 13:00 ET, so the entry is the next cash session at 09:30 ET and
the exit is 15:55 ET that same session. Original term is 10-year,
including reopenings. The auction tail and the bid-to-cover ratio are
not used. Long and short are both rules. Replication is QQQ.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import base_matrix, build_spx as build28, finish, signals_for as signals28
from rare_setups_run29 import build_spx as build29
from rare_setups_run29 import signals_for as signals29
from rare_setups_run30 import build_spx as build30
from rare_setups_run30 import signals_for as signals30
from rare_setups_run31 import build_spx as build31
from rare_setups_run32 import build_spx as build32
from rare_setups_run32 import next_entries, signal_days
from rare_setups_study import build_daily

NEW_CELLS = ("auction_next_long", "auction_next_short")
DATES = Path("data/treasury/ten_year_auction_dates.csv")


def auction_days() -> list[date]:
    frame = pd.read_csv(DATES, parse_dates=["date"])
    return [stamp.date() for stamp in frame["date"]]


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    entries = []
    for day in auction_days():
        entry = next((item for item in tradable if item > day), None)
        if entry is not None and (entry - day).days <= 4:
            entries.append(entry)
    entries = sorted(set(entries))
    return {"auction_next_long": entries, "auction_next_short": list(entries)}


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
    from rare_setups_run20 import open_map
    from rare_setups_run28 import trade_row
    import numpy as np
    book = {name: [] for name in NEW_CELLS}
    qqq = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    sides = {"auction_next_long": 1, "auction_next_short": -1}
    for name in NEW_CELLS:
        side = sides[name]
        for day in signals[name]:
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
    frame = __import__("rare_setups_study", fromlist=["load_daily"]).load_daily(Path("/tmp/rare_data/daily"), "QQQ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = __import__("pandas").DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    qdays = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    for name in NEW_CELLS:
        side = sides[name]
        for day in signals[name]:
            if day not in qdays:
                continue
            i = qdays[day]
            entry_px = float(work["open"].iloc[i])
            exit_px = float(work["close"].iloc[i])
            if entry_px <= 0:
                continue
            qqq[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    matrix.update(build29(state, signals29(state, set(tradable))))
    matrix.update(build30(state, signals30(tradable)))
    matrix.update(build31(state, tradable))
    matrix.update(build32(state, next_entries(signal_days(), tradable)))
    finish(
        lambda name: {"entry": "next session 09:30 ET after the 10-year auction close", "exit": "15:55 ET the same session", "replication": "QQQ"},
        book, qqq, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run33.json"),
        "10-year note competitive close date, including reopenings. Next 09:30 to 15:55. No tail or bid-to-cover filter.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
