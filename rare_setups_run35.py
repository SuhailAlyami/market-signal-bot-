"""Run 35. Fixed before any trade result is computed.

Round 21 tested the share of current S&P members above the 50-day
average. This is the same published threshold on the 200-day average:
the prior 10 sessions dipped below 15%, and today the share crosses
above 45%, with at least 400 names. The signal is known at the close.
Entry is the next session at 09:30 ET. Exit is 15:55 ET ten sessions
later. Long only. Replication is IWM.
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
from rare_setups_study import build_daily, load_daily

NEW_CELLS = ("above200_thrust_long",)
HOLD = 10
DAILY = Path("/tmp/rare_data/daily")


def signals_for(panel: pd.DataFrame) -> dict[str, list[date]]:
    close = panel.sort_index()
    ma = close.rolling(200).mean()
    usable = close.notna() & ma.notna()
    share = ((close > ma) & usable).sum(axis=1) / usable.sum(axis=1).replace(0, np.nan)
    found = []
    values = share.to_numpy()
    counts = usable.sum(axis=1).to_numpy()
    for i in range(11, len(values)):
        window = values[i - 10:i]
        if counts[i] < 400 or not np.isfinite(values[i]):
            continue
        if values[i] > 0.45 and values[i - 1] <= 0.45 and np.nanmin(window) < 0.15:
            found.append(share.index[i].date())
    return {"above200_thrust_long": found}


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
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
            book[name].append(trade_row(entry_day, exit_px - entry_px, entry_px, 1))
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
        for signal_day in signals[name]:
            entry_i = next((i for i, day in enumerate(days) if day > max(signal_day, exit_day)), None)
            if entry_i is None or entry_i + HOLD >= len(days):
                continue
            exit_i = entry_i + HOLD
            entry_px = float(work["open"].iloc[entry_i])
            exit_px = float(work["close"].iloc[exit_i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(days[entry_i], (exit_px - entry_px) / entry_px, entry_px, 1))
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
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    signals = signals_for(panel)
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 10 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run35.json"),
        "Share above the 200-day average crosses 45% after a 10-session low under 15%. The 50-day version was round 21.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
