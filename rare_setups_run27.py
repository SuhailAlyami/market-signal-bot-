"""Run 27. Fixed before any trade result is computed.

Turn-of-month, FOMC, CPI, expiry, Monday and Friday were already tested.
This is the calendar month, not the turn of the month.

Winter months are November through April. Summer months are May through
October. Enter at 09:30 ET on the first cash session of the month. Exit
at 15:55 ET on the last cash session of that same month. Winter is long.
Summer is short. One position, because the exit is before the next entry.

The every-month long is a baseline in the matrix. It is the market drift,
not a candidate. Replication is IWM, same dates, open to close of the
month, with 0.04% subtracted as the doubled cost.
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
from rare_setups_run25 import bar_clears, complete_sessions, fraction_book, keep, prior_books, slim, weekday_bars
from rare_setups_run26 import build_spx as build26
from rare_setups_run26 import signals_for as signals26
from rare_setups_study import COST, build_daily, load_daily

WINTER = {11, 12, 1, 2, 3, 4}
SUMMER = {5, 6, 7, 8, 9, 10}
CANDIDATES = ("winter_month_long", "summer_month_short")
BASELINE = "every_month_long"
NEW_CELLS = CANDIDATES + (BASELINE,)
DAILY = Path("/tmp/rare_data/daily")


def month_spans(days: list[date]) -> list[tuple[date, date, int]]:
    spans = []
    start = 0
    for i, day in enumerate(days):
        if i + 1 == len(days) or days[i + 1].month != day.month:
            spans.append((days[start], day, day.month))
            start = i + 1
    return spans


def build_spx(state, days: list[date]) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for entry_day, exit_day, month in month_spans(days):
        entry_i = opens.get(entry_day)
        exit_i = state["close_i"].get(exit_day)
        if entry_i is None or exit_i is None or exit_i <= entry_i:
            continue
        entry_px = float(state["open"][entry_i])
        exit_px = float(state["close"][exit_i])
        gross = exit_px - entry_px
        book[BASELINE].append({"day": entry_day, "year": entry_day.year, "gross": gross, "side": 1, "entry": entry_px})
        if month in WINTER:
            book["winter_month_long"].append({"day": entry_day, "year": entry_day.year, "gross": gross, "side": 1, "entry": entry_px})
        if month in SUMMER:
            book["summer_month_short"].append({"day": entry_day, "year": entry_day.year, "gross": -gross, "side": -1, "entry": entry_px})
    return book


def build_iwm(last_day: date) -> dict[str, list[dict]]:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    work = work.loc[work.index.date <= last_day]
    days = [stamp.date() for stamp in work.index]
    book = {name: [] for name in NEW_CELLS}
    for entry_day, exit_day, month in month_spans(days):
        entry_i = days.index(entry_day)
        exit_i = days.index(exit_day)
        entry_px = float(work["open"].iloc[entry_i])
        exit_px = float(work["close"].iloc[exit_i])
        if entry_px <= 0 or entry_i == exit_i:
            continue
        gross = (exit_px - entry_px) / entry_px
        book[BASELINE].append({"day": entry_day, "year": entry_day.year, "gross": gross, "side": 1, "entry": entry_px})
        if month in WINTER:
            book["winter_month_long"].append({"day": entry_day, "year": entry_day.year, "gross": gross, "side": 1, "entry": entry_px})
        if month in SUMMER:
            book["summer_month_short"].append({"day": entry_day, "year": entry_day.year, "gross": -gross, "side": -1, "entry": entry_px})
    return book


def main() -> None:
    print("PRE-REGISTERED", CANDIDATES, "baseline", BASELINE, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    days = complete_sessions(state)
    last_day = days[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    book = build_spx(state, days)
    iwm = build_iwm(last_day)
    for name in NEW_CELLS:
        print(" signals", name, len(book[name]), flush=True)
    print("prior family", flush=True)
    yahoo = build_daily(DAILY)[0]
    matrix = prior_books(state, usa, tech, yahoo)
    from rare_setups_run25 import build_spx as build25
    from rare_setups_run25 import signals_for as signals25

    matrix.update(build25(state, signals25(state, set(days))))
    matrix.update(build26(state, signals26(state, days)))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= last_day]
    names, cols, rows = [], [], []
    for name, trades in matrix.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        stress = summarize(keep(book[name], TEST_START, last_day), COST * 2)
        rep = summarize(fraction_book(keep(iwm[name], TEST_START, last_day), 0.0004), 0.0)
        row = {
            "name": name,
            "role": "baseline" if name == BASELINE else "candidate",
            "entry": "09:30 ET on the first cash session of the month",
            "exit": "15:55 ET on the last cash session of the month",
            "test": summarize(keep(book[name], TEST_START, last_day), COST),
            "test_2x": slim(stress),
            "validation": slim(summarize(keep(book[name], VAL_START, VAL_END), COST)),
            "train": slim(summarize(keep(book[name], TRAIN_START, TRAIN_END), COST)),
            "replication_iwm_2x": slim(rep),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep),
        }
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(book[name], calendar, COST))
        print(name, "n", row["test"]["trades"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], "iwm", rep["expectancy"], rep["expectancy_ci"], flush=True)
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
        row["meets_success_bar"] = bool(
            row["role"] == "candidate" and row["spx_bar"] and row["replication_bar"] and row["family_wise"]["survives"]
        )
        if row["meets_success_bar"]:
            passed.append(row["name"])
    payload = {
        "preregistered": list(CANDIDATES),
        "baseline": BASELINE,
        "definition": "Winter is Nov-Apr long. Summer is May-Oct short. First session 09:30 to last session 15:55.",
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
    Path("artifacts/rare_setups/run27.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


if __name__ == "__main__":
    main()
