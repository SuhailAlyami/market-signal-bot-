"""Run 41. Fixed before any trade result is computed.

The 50-day and 200-day member shares, the 90/90 day, and the Zweig
thrust were already tested. This is the 52-week high/low balance.
A name is eligible once it has 252 prior closes. A new high is a close
at or above that prior high. A new low is a close at or below that
prior low.

The ratio is new highs minus new lows, divided by the eligible count.
At least 400 names are required. A ratio of -0.15 or lower is a long.
A ratio of +0.15 or higher is a short. The print is known at the close.
Entry is the next session at 09:30 ET. Exit is 15:55 ET five sessions
later. Replication is IWM.
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
from rare_setups_run34 import build_spx as build34
from rare_setups_run34 import matrix_through_33
from rare_setups_run34 import signals_for as signals34
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_run36 import build_spx as build36
from rare_setups_run36 import signals_for as signals36
from rare_setups_run37 import build_spx as build37
from rare_setups_run37 import signals_for as signals37
from rare_setups_run39 import build_spx as build39
from rare_setups_run39 import signals_for as signals39
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("nhnl_washout_long", "nhnl_blowoff_short")
SIDES = {"nhnl_washout_long": 1, "nhnl_blowoff_short": -1}
HOLD = 5
DAILY = Path("/tmp/rare_data/daily")


def signals_for(panel: pd.DataFrame) -> dict[str, list[date]]:
    close = panel.sort_index()
    prior_max = close.shift(1).rolling(252, min_periods=252).max()
    prior_min = close.shift(1).rolling(252, min_periods=252).min()
    eligible = close.notna() & prior_max.notna() & prior_min.notna()
    count = eligible.sum(axis=1)
    highs = ((close >= prior_max) & eligible).sum(axis=1)
    lows = ((close <= prior_min) & eligible).sum(axis=1)
    ratio = (highs - lows) / count.replace(0, np.nan)
    enough = count >= 400
    return {
        "nhnl_washout_long": [stamp.date() for stamp in ratio.index[(enough & (ratio <= -0.15)).fillna(False)]],
        "nhnl_blowoff_short": [stamp.date() for stamp in ratio.index[(enough & (ratio >= 0.15)).fillna(False)]],
    }


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


def build_iwm(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
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


def later_matrix(state, usa, tech, yahoo, tradable):
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    matrix.update(build36(state, signals36(tradable)))
    matrix.update(build37(state, signals37()))
    matrix.update(build39(state, signals39(tradable)))
    from rare_setups_run40 import signals_for as signals40
    from rare_setups_run20 import open_map
    move = signals40(tradable)
    opens = open_map(state)
    move_book = {name: [] for name in ("move_spike_long", "move_spike_short")}
    sides = {"move_spike_long": 1, "move_spike_short": -1}
    for name, side in sides.items():
        seen = set()
        for day in move[name]:
            if day in seen:
                continue
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            move_book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
            seen.add(day)
    matrix.update(move_book)
    return matrix


def main() -> None:
    print("PRE-REGISTERED", NEW_CELLS, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    signals = signals_for(panel)
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = later_matrix(state, usa, tech, yahoo, tradable)
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 5 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run41.json"),
        "52-week new highs minus new lows, divided by eligible names. -0.15 long, +0.15 short. Put/call still ends 2019-10-04.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
