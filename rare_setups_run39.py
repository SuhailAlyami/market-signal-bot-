"""Run 39. Fixed before any trade result is computed.

Dollar ETF impulses and the copper/gold ratio were round 25. Gold there
was only the denominator. Crude oil was not a lead. This round is the
futures daily return, known before the next New York cash open.

Oil uses a 2% impulse. Gold uses 1%. Up is long. Down is short. Entry
is 09:30 ET. Exit is 15:55 ET the same session. Replication is IWM.
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
from rare_setups_run28 import finish, lead_days, series_return, trade_row
from rare_setups_run34 import matrix_through_33
from rare_setups_run34 import build_spx as build34
from rare_setups_run34 import signals_for as signals34
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_run36 import build_spx as build36
from rare_setups_run36 import signals_for as signals36
from rare_setups_run37 import build_spx as build37
from rare_setups_run37 import signals_for as signals37
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("oil_up_long", "oil_down_short", "gold_up_long", "gold_down_short")
SIDES = {name: (1 if name.endswith("long") else -1) for name in NEW_CELLS}
DAILY = Path("/tmp/rare_data/daily")


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    oil_long, oil_short = lead_days(series_return("CL_F"), tradable, 0.02)
    gold_long, gold_short = lead_days(series_return("GC_F"), tradable, 0.01)
    return {
        "oil_up_long": oil_long,
        "oil_down_short": oil_short,
        "gold_up_long": gold_long,
        "gold_down_short": gold_short,
    }


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        side = SIDES[name]
        seen = set()
        for day in signals[name]:
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


def build_iwm(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        seen = set()
        for day in signals[name]:
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
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    matrix.update(build36(state, signals36(tradable)))
    matrix.update(build37(state, signals37()))
    finish(
        lambda name: {"entry": "09:30 ET", "exit": "15:55 ET the same session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run39.json"),
        "Crude oil 2% and gold 1% daily futures returns. Next cash session, flat at 15:55. Dollar and copper/gold were round 25.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
