"""Run 60. Fixed before any trade result is computed.

Yen and euro leveraged-fund positioning were round 53. This is the
British pound in the same CFTC financial report, not the dollar index
and not the yen. The report date is Tuesday. The release is three days
later. Entry is 18:00 ET on the first cash session on or after that
Friday. Exit is 15:55 ET five sessions later.

The thresholds are the ones already locked for the other currencies:
leveraged-fund net at or below the 10th percentile of the prior 52
reports is a crowded short of the pound, and the S&P trade is short.
Net at or above the 90th percentile is a crowded long of the pound, and
the S&P trade is long. They were not refit on sterling. Replication is
EZU at the next cash open. One position until exit.
"""
from __future__ import annotations

import zipfile
from datetime import date
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

from rare_setups_run13 import entry_stamp
from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import first_session_on_or_after
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
from rare_setups_run59 import build_spx as build59
from rare_setups_run59 import signals_for as signals59
from rare_setups_study import build_daily, load_daily

MARKET = "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE"
NEW_CELLS = ("gbp_lev_low_short", "gbp_lev_high_long")
SIDES = {"gbp_lev_low_short": -1, "gbp_lev_high_long": 1}
HOLD = 5
DAILY = Path("/tmp/rare_data/daily")


def fx_cot() -> pd.DataFrame:
    rows = []
    for path in sorted(Path("/tmp/rare_data/external/cftc").glob("fut_fin_*.zip")):
        if path.stat().st_size < 1000:
            continue
        with zipfile.ZipFile(path) as archive:
            raw = archive.read(archive.namelist()[0]).decode("latin1", errors="replace")
        frame = pd.read_csv(StringIO(raw))
        frame.columns = [col.strip().strip('"') for col in frame.columns]
        name = frame["Market_and_Exchange_Names"].astype(str).str.strip().str.strip('"')
        picked = frame[name.eq(MARKET)].copy()
        if picked.empty:
            continue
        date_col = "Report_Date_as_YYYY-MM-DD" if "Report_Date_as_YYYY-MM-DD" in picked.columns else "Report_Date_as_MM_DD_YYYY"
        picked["asof"] = pd.to_datetime(picked[date_col])
        picked["lev_net"] = picked["Lev_Money_Positions_Long_All"] - picked["Lev_Money_Positions_Short_All"]
        rows.append(picked[["asof", "lev_net"]])
    book = pd.concat(rows, ignore_index=True).dropna()
    return book.drop_duplicates("asof", keep="last").sort_values("asof")


def signals_for() -> dict[str, list[date]]:
    cot = fx_cot()
    values = cot["lev_net"].to_numpy(float)
    low = np.zeros(len(values), dtype=bool)
    high = np.zeros(len(values), dtype=bool)
    for i in range(52, len(values)):
        history = values[i - 52:i]
        low[i] = values[i] <= np.quantile(history, 0.10)
        high[i] = values[i] >= np.quantile(history, 0.90)
    def days(flag):
        return [(pd.Timestamp(stamp) + pd.Timedelta(days=3)).date() for stamp, ok in zip(cot["asof"], flag) if ok]
    return {"gbp_lev_low_short": days(low), "gbp_lev_high_long": days(high)}


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for raw_day in signals[name]:
            day = first_session_on_or_after(state["session_dates"], raw_day)
            if day is None or day <= exit_day:
                continue
            known = state["close_i"].get(day)
            pos = state["pos"].get(day)
            if known is None or pos is None or pos + HOLD >= len(state["session_dates"]):
                continue
            entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
            exit_day = state["session_dates"][pos + HOLD]
            exit_i = state["close_i"].get(exit_day)
            if entry_ts is None or exit_i is None:
                continue
            entry_i = int(state["index"].searchsorted(entry_ts))
            if exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
    return book


def build_ezu(signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "EZU")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for raw_day in signals[name]:
            entry_i = next((i for i, day in enumerate(days) if day > max(raw_day, exit_day)), None)
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
    ezu = build_ezu(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_53(state, usa, tech, yahoo, tradable)
    matrix.update(build54(state, signals54()))
    matrix.update(build55(state, signals55()))
    matrix.update(build56(state, signals56()))
    matrix.update(build57(state, signals57()))
    matrix.update(build58(state, signals58()))
    matrix.update(build59(state, signals59()))
    finish(
        lambda name: {"entry": "18:00 ET on the release Friday", "exit": "15:55 ET, 5 sessions later", "replication": "EZU"},
        book, ezu, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run60.json"),
        "British-pound leveraged-fund net versus the prior 52 reports. A crowded sterling short sells the S&P. A crowded sterling long buys it. Thresholds transferred from the yen rule.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
