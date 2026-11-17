"""Run 34. Fixed before any trade result is computed.

Round 20 used S&P 500 Consolidated positioning. The standalone e-mini
name only starts in February 2022, so it is not a second independent
history and is not a rule here. VIX futures in the same CFTC financial
report were not used.

The report date is Tuesday and the release is three days later. Entry
is 18:00 ET on the first cash session on or after that Friday. Exit is
15:55 ET five sessions later. The percentile uses the prior 52 reports
only.

Leveraged-fund net VIX at or below the 10th percentile is a short in the
S&P. Net at or above the 90th percentile is a long. One position per
rule. QQQ enters at the next cash open because it has no 18:00 print.
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
from rare_setups_run28 import (
    base_matrix,
    build_spx as build28,
    finish,
    signals_for as signals28,
    trade_row,
)
from rare_setups_run29 import build_spx as build29
from rare_setups_run29 import signals_for as signals29
from rare_setups_run30 import build_spx as build30
from rare_setups_run30 import signals_for as signals30
from rare_setups_run31 import build_spx as build31
from rare_setups_run32 import build_spx as build32
from rare_setups_run32 import next_entries, signal_days
from rare_setups_run33 import signals_for as signals33
from rare_setups_study import build_daily

NEW_CELLS = ("vix_lev_low_short", "vix_lev_high_long")
SIDES = {"vix_lev_low_short": -1, "vix_lev_high_long": 1}
HOLD = 5
MARKET = "VIX FUTURES - CBOE FUTURES EXCHANGE"


def vix_cot() -> pd.DataFrame:
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


def release_days(flag: np.ndarray, asof: pd.Series) -> list[date]:
    found = []
    for stamp, ok in zip(asof, flag):
        if ok:
            found.append((pd.Timestamp(stamp) + pd.Timedelta(days=3)).date())
    return found


def signals_for() -> dict[str, list[date]]:
    cot = vix_cot()
    values = cot["lev_net"].to_numpy(float)
    low = np.zeros(len(values), dtype=bool)
    high = np.zeros(len(values), dtype=bool)
    for i in range(52, len(values)):
        history = values[i - 52:i]
        low[i] = values[i] <= np.quantile(history, 0.10)
        high[i] = values[i] >= np.quantile(history, 0.90)
    return {
        "vix_lev_low_short": release_days(low, cot["asof"]),
        "vix_lev_high_long": release_days(high, cot["asof"]),
    }


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


def build_qqq(signals, tradable: list[date], last_day: date) -> dict[str, list[dict]]:
    frame = __import__("rare_setups_study", fromlist=["load_daily"]).load_daily(Path("/tmp/rare_data/daily"), "QQQ")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    qdays = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for raw_day in signals[name]:
            entry = next((day for day in qdays if day > max(raw_day, exit_day)), None)
            if entry is None:
                continue
            entry_i = qdays.index(entry)
            if entry_i + HOLD >= len(qdays):
                continue
            exit_i = entry_i + HOLD
            entry_px = float(work["open"].iloc[entry_i])
            exit_px = float(work["close"].iloc[exit_i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(entry, side * (exit_px - entry_px) / entry_px, entry_px, side))
            exit_day = qdays[exit_i]
    return book


def matrix_through_33(state, usa, tech, yahoo, tradable):
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    matrix.update(build28(state, signals28(tradable)))
    matrix.update(build29(state, signals29(state, set(tradable))))
    matrix.update(build30(state, signals30(tradable)))
    matrix.update(build31(state, tradable))
    matrix.update(build32(state, next_entries(signal_days(), tradable)))
    from rare_setups_run20 import open_map
    auction = signals33(tradable)
    sides = {"auction_next_long": 1, "auction_next_short": -1}
    opens = open_map(state)
    auction_book = {name: [] for name in sides}
    for name, side in sides.items():
        for day in auction[name]:
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            auction_book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
    matrix.update(auction_book)
    return matrix


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
    qqq = build_qqq(signals, tradable, last_day)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    finish(
        lambda name: {"entry": "18:00 ET on the release Friday", "exit": "15:55 ET, 5 sessions later", "replication": "QQQ next open"},
        book, qqq, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run34.json"),
        "VIX futures leveraged-fund net versus the prior 52 reports. 10th percentile shorts the S&P. 90th percentile buys it. E-mini COT is not used because it starts in 2022.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
