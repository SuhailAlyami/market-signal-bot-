"""Run 59. Fixed before any trade result is computed.

Initial claims (ICSA) were round 56. This is continued claims, FRED
CCSA: the stock of insured unemployment, not the weekly flow of new
filings. The observation is the week ending Saturday. The Department of
Labor release is the following Thursday at 08:30 ET, so the entry is
09:30 ET on the first cash session on or after five days later. Exit is
15:55 ET ten sessions later. The window is one quarter, thirteen weeks,
because this is a stock rather than a four-week flow. It was not chosen
after seeing CCSA results.

A thirteen-week change crossing from positive to negative means the
stock of claims has stopped rising. That is a long. The opposite cross
is a short. Replication is EWJ, the next cash open, same hold. One
position until exit. AAII, NAAIM, and the Cboe put/call file are not
usable. This is not the payrolls-Friday calendar and not ICSA.
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
from rare_setups_run54 import build_spx as build54
from rare_setups_run54 import matrix_through_53, signals_for as signals54
from rare_setups_run55 import build_spx as build55
from rare_setups_run55 import signals_for as signals55
from rare_setups_run56 import build_spx as build56
from rare_setups_run56 import signals_for as signals56
from rare_setups_run57 import build_spx as build57
from rare_setups_run57 import signals_for as signals57
from rare_setups_run58 import build_spx as build58
from rare_setups_run58 import signals_for as signals58
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("ccsa_ease_long", "ccsa_rise_short")
SIDES = {"ccsa_ease_long": 1, "ccsa_rise_short": -1}
HOLD = 10
DAILY = Path("/tmp/rare_data/daily")


def signals_for() -> dict[str, list[date]]:
    series = fred_series("CCSA").dropna().sort_index()
    change = series.diff(13)
    ease = (change.shift(1) > 0) & (change < 0)
    rise = (change.shift(1) < 0) & (change > 0)
    return {
        "ccsa_ease_long": [stamp.date() for stamp in series.index[ease.fillna(False)]],
        "ccsa_rise_short": [stamp.date() for stamp in series.index[rise.fillna(False)]],
    }


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for obs in signals[name]:
            entry_day = first_session_on_or_after(state["session_dates"], max(obs + timedelta(days=5), exit_day + timedelta(days=1)))
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


def build_ewj(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "EWJ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for obs in signals[name]:
            raw = obs + timedelta(days=5)
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
    ewj = build_ewj(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_53(state, usa, tech, yahoo, tradable)
    matrix.update(build54(state, signals54()))
    matrix.update(build55(state, signals55()))
    matrix.update(build56(state, signals56()))
    matrix.update(build57(state, signals57()))
    matrix.update(build58(state, signals58()))
    finish(
        lambda name: {"entry": "09:30 ET on the release Thursday", "exit": "15:55 ET, 10 sessions later", "replication": "EWJ"},
        book, ewj, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run59.json"),
        "CCSA thirteen-week change crossing zero. Thursday 08:30 release, traded at 09:30. Not initial claims and not payrolls Friday.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
