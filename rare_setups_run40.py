"""Run 40. Fixed before any trade result is computed.

The ICE BofA MOVE index is the Treasury rate-volatility proxy. A day
when MOVE rises at least 5% is the event. The print is known before the
next New York cash open. One rule buys that next session. The other
sells it. Both are pre-registered, so the sign is not chosen later.
Entry is 09:30 ET. Exit is 15:55 ET the same session. Replication is IWM.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run25 import complete_sessions, weekday_bars
from rare_setups_run28 import finish, lead_days, series_return
from rare_setups_run34 import matrix_through_33
from rare_setups_run34 import build_spx as build34
from rare_setups_run34 import signals_for as signals34
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_run36 import build_spx as build36
from rare_setups_run36 import signals_for as signals36
from rare_setups_run37 import build_spx as build37
from rare_setups_run37 import signals_for as signals37
from rare_setups_run39 import build_iwm, build_spx as build39
from rare_setups_run39 import signals_for as signals39
from rare_setups_study import build_daily

NEW_CELLS = ("move_spike_long", "move_spike_short")


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    spike, _down = lead_days(series_return("MOVE"), tradable, 0.05)
    return {"move_spike_long": spike, "move_spike_short": list(spike)}


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
    # build_spx in run39 uses its own NEW_CELLS. Build locally with that helper's loop by a thin map.
    from rare_setups_run20 import open_map
    from rare_setups_run28 import trade_row
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    sides = {"move_spike_long": 1, "move_spike_short": -1}
    for name in NEW_CELLS:
        side = sides[name]
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
    frame = __import__("rare_setups_study", fromlist=["load_daily"]).load_daily(Path("/tmp/rare_data/daily"), "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    iwm = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = sides[name]
        seen = set()
        for day in signals[name]:
            if day not in days or day in seen:
                continue
            i = days[day]
            entry_px = float(work["open"].iloc[i])
            exit_px = float(work["close"].iloc[i])
            if entry_px <= 0:
                continue
            iwm[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
            seen.add(day)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    matrix.update(build36(state, signals36(tradable)))
    matrix.update(build37(state, signals37()))
    matrix.update(build39(state, signals39(tradable)))
    finish(
        lambda name: {"entry": "09:30 ET the session after MOVE rises 5%", "exit": "15:55 ET the same session", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run40.json"),
        "MOVE up at least 5%. Both the long and the short are pre-registered. Next 09:30 to 15:55.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
