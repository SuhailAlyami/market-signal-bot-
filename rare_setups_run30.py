"""Run 30. Fixed before any trade result is computed.

Monthly options-expiration week was already tested, for every third
Friday. This round is only the quarterly expiration, the third Friday
of March, June, September, and December. Entry is 09:30 ET on the first
cash session of that week, at most four calendar days before the Friday.
Exit is 15:55 ET on the Friday. Long and short are both rules. One
position per week. Replication is QQQ.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import open_map
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import base_matrix, build_spx as build28, finish, replica, signals_for as signals28
from rare_setups_run29 import build_spx as build29
from rare_setups_run29 import signals_for as signals29
from rare_setups_study import build_daily, third_fridays

NEW_CELLS = ("quad_week_long", "quad_week_short")
SIDES = {"quad_week_long": 1, "quad_week_short": -1}


def signals_for(days: list[date]) -> dict[str, list[date]]:
    fridays = [day for day in third_fridays(pd.DatetimeIndex(pd.to_datetime(days))) if day.month in (3, 6, 9, 12)]
    entries = []
    for friday in fridays:
        week = [day for day in days if friday >= day and (friday - day).days <= 4 and day.weekday() <= 4]
        if not week or friday not in days:
            continue
        entries.append(week[0])
    return {"quad_week_long": entries, "quad_week_short": list(entries)}


def build_spx(state, signals) -> dict[str, list[dict]]:
    from rare_setups_run28 import trade_row
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    fridays = {day for day in third_fridays(pd.DatetimeIndex(pd.to_datetime(state["session_dates"]))) if day.month in (3, 6, 9, 12)}
    for name in NEW_CELLS:
        side = SIDES[name]
        for entry_day in signals[name]:
            friday = next((day for day in state["session_dates"] if day in fridays and day >= entry_day and (day - entry_day).days <= 4), None)
            entry_i = opens.get(entry_day)
            exit_i = state["close_i"].get(friday) if friday else None
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(entry_day, side * (exit_px - entry_px), entry_px, side))
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
    from rare_setups_run28 import trade_row
    import numpy as np
    frame = __import__("rare_setups_study", fromlist=["load_daily"]).load_daily(Path("/tmp/rare_data/daily"), "QQQ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = __import__("pandas").DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    qdays = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    qbook = {name: [] for name in NEW_CELLS}
    fridays = {day for day in third_fridays(__import__("pandas").DatetimeIndex(__import__("pandas").to_datetime(qdays))) if day.month in (3, 6, 9, 12)}
    for name in NEW_CELLS:
        side = SIDES[name]
        for entry_day in signals[name]:
            if entry_day not in qdays:
                continue
            friday = next((day for day in qdays if day in fridays and day >= entry_day and (day - entry_day).days <= 4), None)
            if friday is None:
                continue
            entry_px = float(work.loc[work.index.date == entry_day, "open"].iloc[0])
            exit_px = float(work.loc[work.index.date == friday, "close"].iloc[0])
            if entry_px <= 0:
                continue
            qbook[name].append(trade_row(entry_day, side * (exit_px - entry_px) / entry_px, entry_px, side))
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    matrix.update(build29(state, signals29(state, set(tradable))))
    finish(
        lambda name: {"entry": "09:30 ET on the first session of quad-witching week", "exit": "15:55 ET on that Friday", "replication": "QQQ"},
        book, qbook, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run30.json"),
        "Only the third Friday of March, June, September, and December. Monthly expiration weeks are not repeated.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
