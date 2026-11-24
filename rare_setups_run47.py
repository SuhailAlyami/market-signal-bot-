"""Run 47. Fixed before any trade result is computed.

XLY/XLP and XLU/XLK were round 25. This is semiconductors versus the
S&P, SMH divided by SPY, using adjusted closes. A 1% rise in that ratio
is a long in the S&P the next cash session. A 1% fall is a short. Entry
is 09:30 ET. Exit is 15:55 ET the same session. Replication is IWM,
not QQQ, because QQQ is heavy in the same semiconductors.
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
from rare_setups_run28 import finish, lead_days, trade_row
from rare_setups_run41 import later_matrix
from rare_setups_run41 import build_spx as build41
from rare_setups_run41 import signals_for as signals41
from rare_setups_run42 import build_spx as build42
from rare_setups_run42 import next_entries, signal_days
from rare_setups_run43 import build_spx as build43
from rare_setups_run43 import signals_for as signals43
from rare_setups_run45 import build_spx as build45
from rare_setups_run45 import signals_for as signals45
from rare_setups_run46 import build_spx as build46
from rare_setups_run46 import signals_for as signals46
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("semis_up_long", "semis_down_short")
SIDES = {"semis_up_long": 1, "semis_down_short": -1}
DAILY = Path("/tmp/rare_data/daily")


def ratio_return() -> pd.Series:
    def adjusted(stem: str) -> pd.Series:
        frame = load_daily(DAILY, stem)
        for column in ("Adj close", "Adj Close", "Close"):
            if column in frame.columns:
                series = frame[column]
                break
        else:
            series = frame["Close"]
        series = series.sort_index()
        return series[~series.index.duplicated(keep="last")]
    ratio = (adjusted("SMH") / adjusted("SPY")).dropna().sort_index()
    return ratio.pct_change()


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    longs, shorts = lead_days(ratio_return(), tradable, 0.01)
    return {"semis_up_long": longs, "semis_down_short": shorts}


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


def matrix_through_46(state, usa, tech, yahoo, tradable):
    matrix = later_matrix(state, usa, tech, yahoo, tradable)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build41(state, signals41(panel)))
    matrix.update(build42(state, next_entries(signal_days(), tradable)))
    matrix.update(build43(state, signals43(panel)))
    matrix.update(build45(state, signals45()))
    matrix.update(build46(state, signals46()))
    return matrix


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
    matrix = matrix_through_46(state, usa, tech, yahoo, tradable)
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET the same session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run47.json"),
        "SMH/SPY adjusted-close ratio moves at least 1%. Next 09:30 to 15:55. XLY/XLP and XLU/XLK are not repeated.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
