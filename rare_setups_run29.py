"""Run 29. Fixed before any trade result is computed.

VIX term structure was round 20. This is the gap between the VIX close
and the S&P's own 20-session realized volatility. Realized volatility is
the standard deviation of the last 20 session returns, including today,
times the square root of 252, in points. Both numbers are known at the
cash close. Entry is the next session at 09:30 ET. Exit is 15:55 ET five
sessions later. One position per rule.

Long when VIX exceeds realized volatility by 5 points. Short when
realized volatility exceeds VIX by 5 points. Replication is IWM.
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
from rare_setups_run28 import base_matrix, build_spx as build28, finish, replica, signals_for as signals28
from rare_setups_study import build_daily, load_daily

GAP = 5.0
HOLD = 5
NEW_CELLS = ("vix_rich_long", "rv_rich_short")
DAILY = Path("/tmp/rare_data/daily")


def session_returns(state) -> list[tuple[date, float]]:
    found = []
    previous = None
    for day in state["session_dates"]:
        close_i = state["close_i"].get(day)
        if close_i is None:
            continue
        price = float(state["close"][close_i])
        if previous not in (None, 0):
            found.append((day, price / previous - 1))
        previous = price
    return found


def signals_for(state, tradable: set[date]) -> dict[str, list[date]]:
    vix = load_daily(DAILY, "VIX")["Close"].sort_index()
    vix = vix[~vix.index.duplicated(keep="last")]
    vix_by_day = {stamp.date(): float(value) for stamp, value in vix.dropna().items()}
    rows = session_returns(state)
    book = {name: [] for name in NEW_CELLS}
    for i in range(20, len(rows)):
        day, _value = rows[i]
        if day not in tradable or day not in vix_by_day:
            continue
        window = [value for _day, value in rows[i - 19:i + 1]]
        realized = float(np.std(window, ddof=1) * np.sqrt(252) * 100)
        gap = vix_by_day[day] - realized
        if gap >= GAP:
            book["vix_rich_long"].append(day)
        elif gap <= -GAP:
            book["rv_rich_short"].append(day)
    return book


def build_spx(state, signals) -> dict[str, list[dict]]:
    from rare_setups_run28 import trade_row
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    sides = {"vix_rich_long": 1, "rv_rich_short": -1}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = sides[name]
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
    from rare_setups_run28 import trade_row
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    work = work.loc[[stamp for stamp in work.index if stamp.date() <= last_day]]
    book = {name: [] for name in NEW_CELLS}
    sides = {"vix_rich_long": 1, "rv_rich_short": -1}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = sides[name]
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
    print("PRE-REGISTERED", NEW_CELLS, "gap", GAP, "hold", HOLD, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    signals = signals_for(state, set(tradable))
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    finish(
        lambda name: {"entry": "next session 09:30 ET", "exit": "15:55 ET, 5 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run29.json"),
        "VIX minus 20-session realized volatility. Long when the gap is at least +5 points. Short when it is at most -5. Next 09:30, exit after 5 sessions.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
