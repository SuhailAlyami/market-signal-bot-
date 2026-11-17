"""Run 53. Fixed before any trade result is computed.

S&P, VIX, and Nasdaq-100 positioning were already tested. This is yen
and euro futures in the same CFTC financial report. The report date is
Tuesday. The release is three days later. Entry is 18:00 ET on the first
cash session on or after that Friday. Exit is 15:55 ET five sessions later.

Leveraged-fund net at or below the 10th percentile of the prior 52
reports is a crowded short of that currency, and the S&P trade is short.
Net at or above the 90th percentile is a crowded long of that currency,
and the S&P trade is long. Replication is IWM.
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
from rare_setups_run52 import build_spx as build52
from rare_setups_run52 import signals_for as signals52
from rare_setups_study import build_daily, load_daily

MARKETS = {
    "jpy": "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE",
    "eur": "EURO FX - CHICAGO MERCANTILE EXCHANGE",
}
NEW_CELLS = (
    "jpy_lev_low_short",
    "jpy_lev_high_long",
    "eur_lev_low_short",
    "eur_lev_high_long",
)
SIDES = {name: (-1 if name.endswith("short") else 1) for name in NEW_CELLS}
HOLD = 5
DAILY = Path("/tmp/rare_data/daily")


def fx_cot(market: str) -> pd.DataFrame:
    rows = []
    for path in sorted(Path("/tmp/rare_data/external/cftc").glob("fut_fin_*.zip")):
        if path.stat().st_size < 1000:
            continue
        with zipfile.ZipFile(path) as archive:
            raw = archive.read(archive.namelist()[0]).decode("latin1", errors="replace")
        frame = pd.read_csv(StringIO(raw))
        frame.columns = [col.strip().strip('"') for col in frame.columns]
        name = frame["Market_and_Exchange_Names"].astype(str).str.strip().str.strip('"')
        picked = frame[name.eq(market)].copy()
        if picked.empty:
            continue
        date_col = "Report_Date_as_YYYY-MM-DD" if "Report_Date_as_YYYY-MM-DD" in picked.columns else "Report_Date_as_MM_DD_YYYY"
        picked["asof"] = pd.to_datetime(picked[date_col])
        picked["lev_net"] = picked["Lev_Money_Positions_Long_All"] - picked["Lev_Money_Positions_Short_All"]
        rows.append(picked[["asof", "lev_net"]])
    book = pd.concat(rows, ignore_index=True).dropna()
    return book.drop_duplicates("asof", keep="last").sort_values("asof")


def tail_days(cot: pd.DataFrame) -> tuple[list[date], list[date]]:
    values = cot["lev_net"].to_numpy(float)
    low = np.zeros(len(values), dtype=bool)
    high = np.zeros(len(values), dtype=bool)
    for i in range(52, len(values)):
        history = values[i - 52:i]
        low[i] = values[i] <= np.quantile(history, 0.10)
        high[i] = values[i] >= np.quantile(history, 0.90)
    def days(flag):
        return [(pd.Timestamp(stamp) + pd.Timedelta(days=3)).date() for stamp, ok in zip(cot["asof"], flag) if ok]
    return days(low), days(high)


def signals_for() -> dict[str, list[date]]:
    found = {}
    for stem, market in MARKETS.items():
        low, high = tail_days(fx_cot(market))
        found[f"{stem}_lev_low_short"] = low
        found[f"{stem}_lev_high_long"] = high
    return found


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
    iwm = build_iwm(signals, last_day)
    yahoo = build_daily(DAILY)[0]
    from rare_setups_run47 import matrix_through_46
    from rare_setups_run47 import build_spx as build47
    from rare_setups_run47 import signals_for as signals47
    from rare_setups_run48 import build_spx as build48
    from rare_setups_run48 import signals_for as signals48
    from rare_setups_run49 import build_spx as build49
    from rare_setups_run49 import signals_for as signals49
    from rare_setups_run51 import build_spx as build51
    from rare_setups_run51 import signals_for as signals51
    matrix = matrix_through_46(state, usa, tech, yahoo, tradable)
    matrix.update(build47(state, signals47(tradable)))
    matrix.update(build48(state, signals48()))
    matrix.update(build49(state, signals49(tradable)))
    matrix.update(build51(state, signals51()))
    matrix.update(build52(state, signals52()))
    finish(
        lambda name: {"entry": "18:00 ET on the release Friday", "exit": "15:55 ET, 5 sessions later", "replication": "IWM"},
        book, iwm, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run53.json"),
        "Yen and euro leveraged-fund net versus the prior 52 reports. A crowded currency short sells the S&P. A crowded currency long buys it.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
