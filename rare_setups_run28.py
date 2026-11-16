"""Run 28. Fixed before any trade result is computed.

USDJPY was only a filter on a 5-minute Keltner rule in the 24-hour
study. Bitcoin and AUDJPY were not leads into the New York open.
Nikkei, Hang Seng, and DAX were round 26. This is not that family.

The signal is the last completed daily return strictly before the cash
session, and no more than three calendar days old. Bitcoin uses a 2%
impulse. AUDJPY uses 0.7%. Entry is 09:30 ET. Exit is 15:55 ET the same
session. Up is long. Down is short. One trade per day.

Replication is QQQ, same entry date, open to close, with 0.04%
subtracted as the doubled cost. CNN's fear-and-greed endpoint returned
418 and is not a rule. AAII stayed blocked.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START
from rare_setups_run14 import prepare_paths
from rare_setups_run16 import TRAIN_END, TRAIN_START
from rare_setups_run17 import load_bars, summarize
from rare_setups_run18 import symbol_paths
from rare_setups_run20 import open_map
from rare_setups_run25 import (
    bar_clears,
    build_spx as build25,
    complete_sessions,
    fraction_book,
    keep,
    prior_books,
    signals_for as signals25,
    slim,
    weekday_bars,
)
from rare_setups_run26 import build_spx as build26
from rare_setups_run26 import signals_for as signals26
from rare_setups_run27 import build_spx as build27
from rare_setups_study import COST, build_daily, load_daily

DAILY = Path("/tmp/rare_data/daily")
NEW_CELLS = ("btc_up_long", "btc_down_short", "audjpy_up_long", "audjpy_down_short")
SIDES = {name: (1 if name.endswith("_long") else -1) for name in NEW_CELLS}
IMPULSE = {"btc": 0.02, "audjpy": 0.007}


def series_return(stem: str) -> pd.Series:
    frame = load_daily(DAILY, stem)
    close = frame["Close"].sort_index()
    close = close[~close.index.duplicated(keep="last")]
    return close.pct_change()


def lead_days(change: pd.Series, tradable: list[date], impulse: float) -> tuple[list[date], list[date]]:
    points = [(stamp.date(), float(value)) for stamp, value in change.dropna().items()]
    longs, shorts = [], []
    cursor = 0
    for day in tradable:
        while cursor + 1 < len(points) and points[cursor + 1][0] < day:
            cursor += 1
        if not points or points[cursor][0] >= day:
            continue
        signal_day, value = points[cursor]
        if (day - signal_day).days > 3:
            continue
        if value >= impulse:
            longs.append(day)
        elif value <= -impulse:
            shorts.append(day)
    return longs, shorts


def signals_for(tradable: list[date]) -> dict[str, list[date]]:
    btc_long, btc_short = lead_days(series_return("BTC_USD"), tradable, IMPULSE["btc"])
    fx_long, fx_short = lead_days(series_return("AUDJPY"), tradable, IMPULSE["audjpy"])
    return {
        "btc_up_long": btc_long,
        "btc_down_short": btc_short,
        "audjpy_up_long": fx_long,
        "audjpy_down_short": fx_short,
    }


def trade_row(day: date, gross: float, entry: float, side: int) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": side, "entry": float(entry)}


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        side = SIDES[name]
        for day in signals[name]:
            entry_i = opens.get(day)
            exit_i = state["close_i"].get(day)
            if entry_i is None or exit_i is None or exit_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(day, side * (exit_px - entry_px), entry_px, side))
    return book


def replica(stem: str, signals, last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, stem)
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = {stamp.date(): i for i, stamp in enumerate(work.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        for day in signals[name]:
            if day not in days:
                continue
            i = days[day]
            entry_px = float(work["open"].iloc[i])
            exit_px = float(work["close"].iloc[i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
    return book


def base_matrix(state, usa, tech, yahoo, tradable):
    matrix = prior_books(state, usa, tech, yahoo)
    matrix.update(build25(state, signals25(state, set(tradable))))
    matrix.update(build26(state, signals26(state, tradable)))
    matrix.update(build27(state, tradable))
    return matrix


def finish(rows_source, book, replica_book, matrix, yahoo, last_day, path: Path, definition: str, cells) -> None:
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= last_day]
    names, cols, rows = [], [], []
    for name, trades in matrix.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in cells:
        test = summarize(keep(book[name], TEST_START, last_day), COST)
        stress = summarize(keep(book[name], TEST_START, last_day), COST * 2)
        rep = summarize(fraction_book(keep(replica_book[name], TEST_START, last_day), 0.0004), 0.0)
        row = {
            "name": name,
            "side": "short" if name.endswith("short") else "long",
            "test": test,
            "test_2x": slim(stress),
            "validation": slim(summarize(keep(book[name], VAL_START, VAL_END), COST)),
            "train": slim(summarize(keep(book[name], TRAIN_START, TRAIN_END), COST)),
            "replication_2x": slim(rep),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep),
        }
        row.update(rows_source(name))
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(book[name], calendar, COST))
        print(name, "n", test["trades"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], "rep", rep["trades"], rep["expectancy"], rep["expectancy_ci"], flush=True)
    mat = np.column_stack(cols)
    best = int(np.nanargmax(np.nan_to_num(mat.mean(0), nan=-1e9)))
    reality = whites_reality_check(mat, float(mat[:, best].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    dsr = deflated_sharpe_of(mat[:, best], sr_star)
    for row in rows:
        col = names.index(row["name"])
        own = whites_reality_check(mat, float(mat[:, col].mean()))
        own_dsr = deflated_sharpe_of(mat[:, col], sr_star)
        row["family_wise"] = {"reality_p": own["p_value"], "dsr": own_dsr["dsr"], "survives": bool(own["survives"] and own_dsr["survives"])}
        row["meets_success_bar"] = bool(row["spx_bar"] and row["replication_bar"] and row["family_wise"]["survives"])
        if row["meets_success_bar"]:
            passed.append(row["name"])
    payload = {
        "preregistered": list(cells),
        "definition": definition,
        "blocked": "CNN fear-and-greed returned 418. AAII previously returned 403.",
        "test_end": str(last_day),
        "matrix_rules": int(len(names)),
        "run13_timing_cells_not_recomputed": 39,
        "family_total_with_run13": int(len(names) + 39),
        "rows": rows,
        "any_meets_success_bar": bool(passed),
        "passed": passed,
        "best_mean_rule": names[best],
        "reality_check_best": reality,
        "deflated_sharpe_best": {key: value for key, value in dsr.items() if key != "trial_sharpes"},
        "live_default": "legacy",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


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
    qqq = replica("QQQ", signals, last_day)
    yahoo = build_daily(DAILY)[0]
    matrix = base_matrix(state, usa, tech, yahoo, tradable)
    finish(
        lambda name: {"entry": "09:30 ET", "exit": "15:55 ET the same session", "replication": "QQQ"},
        book, qqq, matrix, yahoo, last_day,
        Path("artifacts/rare_setups/run28.json"),
        "Last BTC daily return of at least 2%, or AUDJPY of at least 0.7%, known before the cash open. Same-session 09:30 to 15:55.",
        NEW_CELLS,
    )


if __name__ == "__main__":
    main()
