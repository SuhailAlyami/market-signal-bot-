"""Run 22. Fixed before the results are computed.

No company-level earnings feed is free here. The earnings window is the
week that contains the 15th of January, April, July and October, which
is when the large reporters are normally in the tape. NFP week is the
cash week that ends on the first Friday of the month. CPI day and FOMC
day were already tested and are not repeated.

1. earnings_peak_week. Enter 09:30 on the first cash session of that
   week. Exit at the 15:55 close five sessions later.
2. nfp_week_long. Enter 09:30 on the first cash session of the week and
   exit at that Friday's 15:55 close. The jobs report is Friday morning,
   so the trade holds into the release and through that session.

Time exits only. Replication is the same dates on USATECH.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import live_bar
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, stop_book, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_run19 import weekly_book
from rare_setups_run20 import (
    bar_clears,
    build_signals,
    features as prior_features,
    net_of_fraction,
    open_map,
    slim,
    summarize,
)
from rare_setups_run21 import breadth_days
from rare_setups_study import COST, build_daily

NEW_CELLS = ("earnings_peak_week", "nfp_week_long")


def first_on_or_after(dates, day):
    for item in dates:
        if item >= day:
            return item
    return None


def calendars(dates: list[date]) -> dict[str, list[date]]:
    earnings = []
    for year in range(2012, 2027):
        for month in (1, 4, 7, 10):
            fifteenth = date(year, month, 15)
            monday = fifteenth - timedelta(days=fifteenth.weekday())
            session = first_on_or_after(dates, monday)
            if session is not None and session.month == month:
                earnings.append(session)
    nfp = []
    for year in range(2012, 2027):
        for month in range(1, 13):
            fridays = [date(year, month, day) for day in range(1, 8) if date(year, month, day).weekday() == 4]
            if not fridays:
                continue
            monday = fridays[0] - timedelta(days=4)
            session = first_on_or_after(dates, monday)
            friday = first_on_or_after(dates, fridays[0])
            if session is not None and friday is not None and session <= friday and session.month == month:
                nfp.append(session)
    return {"earnings_peak_week": earnings, "nfp_week_long": nfp}


def enter(state, day, ahead, opens):
    pos = state["pos"].get(day)
    entry_i = opens.get(day)
    if pos is None or entry_i is None or pos + ahead >= len(state["session_dates"]):
        return None
    exit_i = state["close_i"].get(state["session_dates"][pos + ahead])
    if exit_i is None or exit_i <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    return {"day": day, "year": day.year, "gross": float(state["close"][exit_i] - entry_px), "side": 1, "entry": entry_px}


def build(state, days):
    opens = open_map(state)
    book = {name: [] for name in NEW_CELLS}
    holds = {"earnings_peak_week": 5, "nfp_week_long": 4}
    for name, ahead in holds.items():
        exit_day = date(1900, 1, 1)
        for day in days[name]:
            if day <= exit_day:
                continue
            row = enter(state, day, ahead, opens)
            if row is None:
                continue
            book[name].append(row)
            exit_day = state["session_dates"][state["pos"][day] + ahead]
    return book


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    state = prepare_paths(usa)
    days = calendars(state["session_dates"])
    for name in NEW_CELLS:
        print(" signals", name, len(days[name]), flush=True)
    book = build(state, days)
    tech_book = build(prepare_paths(tech), days)
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    test_end = max(stamp.date() for stamp in yahoo.index if stamp.date() <= date(2026, 11, 12))
    import rare_setups_run20 as r20
    import rare_setups_run21 as r21
    cells, holds = r20.NEW_CELLS, dict(r20.HOLDS)
    earlier = prior_features()
    earlier.pop("_ranges")
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    prior20 = build_signals(state, earlier)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    breadth = breadth_days(panel)
    r20.NEW_CELLS, r20.HOLDS = r21.NEW_CELLS, r21.HOLDS
    prior21 = build_signals(state, breadth)
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    matrix = old_tradebook(yahoo, symbol_paths("usa500")[0])
    matrix.update(new_tradebook(yahoo, usa))
    matrix.update(target_book(state))
    matrix.update(window_book(state))
    matrix.update(calendar_book(state))
    matrix.update(trend_book(usa))
    matrix.update(build_book(state, cross_asset(Path("/tmp/rare_data/daily")), state["close"]))
    matrix.update(stop_book(state))
    matrix.update(vwap_book(state))
    matrix.update(lead_lag(usa, tech))
    matrix.update(opening_fade(usa))
    matrix.update(weekly_book(state))
    matrix.update(prior20)
    matrix.update(prior21)
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= test_end]
    names, cols, rows = [], [], []
    for name, trades in matrix.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        test = summarize(keep(book[name], TEST_START, test_end), COST)
        stress = summarize(keep(book[name], TEST_START, test_end), COST * 2)
        rep = summarize(net_of_fraction(keep(tech_book[name], TEST_START, test_end), 0.0004), 0.0)
        row = {
            "name": name,
            "entry": "09:30 ET",
            "exit": "15:55 ET, five sessions later" if name == "earnings_peak_week" else "15:55 ET that Friday",
            "test": test,
            "test_2x": slim(stress),
            "replication_usatech_2x": slim(rep),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep),
        }
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(book[name], calendar, COST))
        print(name, "n", test["trades"], "win", test["win_rate"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], flush=True)
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
        "preregistered": list(NEW_CELLS),
        "calendar_limit": "No company earnings dates. The earnings window is the week containing the 15th of January, April, July and October. NFP is the first Friday.",
        "matrix_rules": int(len(names)),
        "run13_timing_cells_not_recomputed": 39,
        "family_total_with_run13": int(len(names) + 39),
        "rows": rows,
        "any_meets_success_bar": bool(passed),
        "passed": passed,
        "best_mean_rule": names[best],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items() if k != "trial_sharpes"},
        "live_default": "legacy",
        "blocked_remaining": "FRED liquidity and HY spread timed out. AAII returned 403. Cboe put/call CSVs end 2019-10-04.",
    }
    Path("artifacts/rare_setups/run22.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


if __name__ == "__main__":
    main()
