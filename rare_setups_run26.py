"""Run 26. Fixed before any trade result is computed.

Asia and Europe cash indexes were not a lead in runs 1-25. Tokyo and
Hong Kong are closed before the New York cash open on the same calendar
date. Frankfurt's cash close is 11:30 ET, so the DAX signal is the prior
session and the entry is the next New York open.

A signal is a daily index return of at least 1% up or 1% down. It is
taken only when the S&P overnight move, from the prior 15:55 close to
the 09:30 open, is inside +/-0.15%. Entry is 09:30 ET. Exit is 15:55 ET
the same session. One trade per day. Long when the foreign index rose,
short when it fell.

Nikkei and Hang Seng enter on the same New York date. If New York is
shut, that signal is dropped. DAX enters the next New York session, and
only when that session is at most four calendar days later.

Replication is IWM, same entry date, open to close, with 0.04%
subtracted as the doubled round-trip cost. The matrix adds these six
rules to every rule through round 25.
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
from rare_setups_study import COST, build_daily, load_daily

IMPULSE = 0.01
QUIET = 0.0015
DAILY = Path("/tmp/rare_data/daily")
NEW_CELLS = (
    "nikkei_up_long",
    "nikkei_down_short",
    "hsi_up_long",
    "hsi_down_short",
    "dax_up_long",
    "dax_down_short",
)
SIDES = {name: (1 if name.endswith("_long") else -1) for name in NEW_CELLS}


def index_return(stem: str) -> pd.Series:
    frame = load_daily(DAILY, stem)
    close = frame["Close"].sort_index()
    close = close[~close.index.duplicated(keep="last")]
    return close.pct_change()


def signals_for(state, tradable: list[date]) -> dict[str, list[date]]:
    """Values are entry dates, not the foreign session dates."""
    tradable_set = set(tradable)
    pos = {day: i for i, day in enumerate(tradable)}
    opens = open_map(state)
    overnight = {}
    previous = None
    for day in tradable:
        close_i = state["close_i"].get(day)
        entry_i = opens.get(day)
        if previous is not None and entry_i is not None and close_i is not None:
            prior_close = float(state["close"][state["close_i"][previous]])
            entry_px = float(state["open"][entry_i])
            if prior_close:
                overnight[day] = entry_px / prior_close - 1
        if close_i is not None:
            previous = day
    book = {name: [] for name in NEW_CELLS}
    same_day = {"nikkei": index_return("N225"), "hsi": index_return("HSI")}
    for stem, change in same_day.items():
        for stamp, value in change.dropna().items():
            day = stamp.date()
            if day not in tradable_set or day not in overnight or abs(overnight[day]) > QUIET:
                continue
            if float(value) >= IMPULSE:
                book[f"{stem}_up_long"].append(day)
            elif float(value) <= -IMPULSE:
                book[f"{stem}_down_short"].append(day)
    dax = index_return("GDAXI")
    for stamp, value in dax.dropna().items():
        signal_day = stamp.date()
        entry = next((day for day in tradable if day > signal_day), None)
        if entry is None or (entry - signal_day).days > 4:
            continue
        if entry not in overnight or abs(overnight[entry]) > QUIET:
            continue
        if float(value) >= IMPULSE:
            book["dax_up_long"].append(entry)
        elif float(value) <= -IMPULSE:
            book["dax_down_short"].append(entry)
    for name in book:
        book[name] = sorted(set(book[name]))
    return book


def trade_row(day: date, gross: float, entry: float, side: int) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": side, "entry": float(entry)}


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


def iwm_frame() -> pd.DataFrame:
    frame = load_daily(DAILY, "IWM")
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    out = pd.DataFrame({"open": frame["Open"] * factor, "close": close}, index=frame.index)
    return out.dropna().sort_index()


def build_iwm(frame: pd.DataFrame, signals, last_day: date) -> dict[str, list[dict]]:
    days = {stamp.date(): i for i, stamp in enumerate(frame.index) if stamp.date() <= last_day}
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        side = SIDES[name]
        for day in signals[name]:
            if day not in days or day > last_day:
                continue
            i = days[day]
            entry_px = float(frame["open"].iloc[i])
            exit_px = float(frame["close"].iloc[i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(day, side * (exit_px - entry_px) / entry_px, entry_px, side))
    return book


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS), flush=True)
    for name in NEW_CELLS:
        print(" -", name, "side", SIDES[name], flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    signals = signals_for(state, tradable)
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    iwm = build_iwm(iwm_frame(), signals, last_day)
    print("prior family", flush=True)
    yahoo = build_daily(DAILY)[0]
    matrix = prior_books(state, usa, tech, yahoo)
    from rare_setups_run25 import build_spx as build25
    from rare_setups_run25 import signals_for as signals25

    matrix.update(build25(state, signals25(state, set(tradable))))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= last_day]
    names, cols, rows = [], [], []
    for name, trades in matrix.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        test = summarize(keep(book[name], TEST_START, last_day), COST)
        stress = summarize(keep(book[name], TEST_START, last_day), COST * 2)
        val = summarize(keep(book[name], VAL_START, VAL_END), COST)
        train = summarize(keep(book[name], TRAIN_START, TRAIN_END), COST)
        rep = summarize(fraction_book(keep(iwm[name], TEST_START, last_day), 0.0004), 0.0)
        row = {
            "name": name,
            "side": "short" if SIDES[name] < 0 else "long",
            "entry": "09:30 ET",
            "exit": "15:55 ET the same session",
            "test": test,
            "test_2x": slim(stress),
            "validation": slim(val),
            "train": slim(train),
            "replication_iwm_2x": slim(rep),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep),
        }
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(book[name], calendar, COST))
        print(
            name, "n", test["trades"], "win", test["win_rate"],
            "exp2", stress["expectancy"], stress["expectancy_ci"],
            "pf2", stress["profit_factor"], "years", stress["years_positive"],
            "iwm", rep["trades"], rep["expectancy"], rep["expectancy_ci"],
            flush=True,
        )
    mat = np.column_stack(cols)
    best = int(np.nanargmax(np.nan_to_num(mat.mean(0), nan=-1e9)))
    reality = whites_reality_check(mat, float(mat[:, best].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    dsr = deflated_sharpe_of(mat[:, best], sr_star)
    for row in rows:
        col = names.index(row["name"])
        own = whites_reality_check(mat, float(mat[:, col].mean()))
        own_dsr = deflated_sharpe_of(mat[:, col], sr_star)
        row["family_wise"] = {
            "reality_p": own["p_value"],
            "dsr": own_dsr["dsr"],
            "survives": bool(own["survives"] and own_dsr["survives"]),
        }
        row["meets_success_bar"] = bool(row["spx_bar"] and row["replication_bar"] and row["family_wise"]["survives"])
        if row["meets_success_bar"]:
            passed.append(row["name"])
    payload = {
        "preregistered": list(NEW_CELLS),
        "definition": "Foreign daily return of at least 1%. Overnight S&P move inside +/-0.15%. Enter 09:30 ET, exit 15:55 ET. Nikkei and Hang Seng are same-day. DAX is the next session.",
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
    Path("artifacts/rare_setups/run26.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


if __name__ == "__main__":
    main()
