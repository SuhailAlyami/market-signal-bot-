"""Run 19. Fixed before any result is computed.

Weekly and quarter flows, not the daily streak or the every-month turn:

- Two completed weeks each closed below the prior week. Buy the next
  week's first cash open (09:30). One cell holds to Friday's 15:55
  close. One cell also uses a 1% stop and a 1% target, with the stop
  first, and Friday's close if neither is hit.
- A down Monday, known at Monday's cash close. Buy Tuesday's 09:30 and
  sell Friday's 15:55.
- First cash session of a new quarter. Buy 09:30 and sell the close
  three sessions later.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

import numpy as np

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import TRAIN_END, TRAIN_START, calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, stop_book, stopped_path, summarize, trade, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_study import COST, build_daily

NEW_CELLS = (
    "two_down_weeks_hold",
    "two_down_weeks_s0.01_t0.01",
    "down_monday_to_friday",
    "quarter_open_hold3",
)


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def fails_validation(val: dict) -> bool:
    if val.get("trades", 0) < 10:
        return False
    ci = val.get("expectancy_ci") or [None, None]
    return ci[1] is not None and ci[1] < 0


def full_pass(row) -> bool:
    test = row["test"]
    stress = row["test_2x"]
    wci = test.get("win_rate_ci") or [None, None]
    ci = test.get("expectancy_ci") or [None, None]
    ci2 = stress.get("expectancy_ci") or [None, None]
    return bool(
        test.get("trades", 0) >= 20
        and test.get("win_rate") is not None and test["win_rate"] >= 0.70
        and wci[0] is not None and wci[0] > 0.50
        and ci[0] is not None and ci[0] > 0
        and ci2[0] is not None and ci2[0] > 0
        and row["family_wise"]["survives"]
        and not row["validation_failed"]
    )


def slim(row: dict) -> dict:
    return {k: row.get(k) for k in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss")}


def cash_open(state, day: date):
    stamps = state["clocks"].get((9, 30))
    if stamps is None:
        return None
    for ts in stamps:
        if ts.date() == day:
            if not __import__("rare_setups_run13", fromlist=["live_bar"]).live_bar(state["bars"], ts):
                return None
            return int(state["index"].searchsorted(ts))
    return None


def weekly_book(state) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    dates = state["session_dates"]
    weeks: list[list[date]] = []
    current: list[date] = []
    for day in dates:
        if current and pd.Timestamp(day).isocalendar().week != pd.Timestamp(current[-1]).isocalendar().week:
            weeks.append(current)
            current = []
        current.append(day)
    if current:
        weeks.append(current)
    closes = []
    for week in weeks:
        last = state["close_i"].get(week[-1])
        closes.append(None if last is None else float(state["close"][last]))
    for i in range(3, len(weeks)):
        c0, c1, c2 = closes[i - 3], closes[i - 2], closes[i - 1]
        if c0 is None or c1 is None or c2 is None or not (c1 < c0 and c2 < c1):
            continue
        week = weeks[i]
        entry_i = cash_open(state, week[0])
        flat = state["close_i"].get(week[-1])
        if entry_i is None or flat is None or flat <= entry_i:
            continue
        entry_px = float(state["open"][entry_i])
        book["two_down_weeks_hold"].append(trade(week[0], float(state["close"][flat] - entry_px), entry_px))
        gross = stopped_path(state, entry_i, entry_px, 0.01, 0.01, flat, 1)
        book["two_down_weeks_s0.01_t0.01"].append(trade(week[0], gross, entry_px))
    for i, day in enumerate(dates):
        if pd.Timestamp(day).weekday() != 0 or i == 0:
            continue
        prev = dates[i - 1]
        if (day - prev).days > 4:
            continue
        monday_close = state["close_i"].get(day)
        prev_close = state["close_i"].get(prev)
        if monday_close is None or prev_close is None:
            continue
        if state["close"][monday_close] >= state["close"][prev_close]:
            continue
        # Find Friday of this week, or the last session before the next Monday.
        friday = None
        for nxt in dates[i + 1:i + 6]:
            if pd.Timestamp(nxt).weekday() == 4 and (nxt - day).days <= 4:
                friday = nxt
            if pd.Timestamp(nxt).weekday() == 0:
                break
        tuesday = dates[i + 1] if i + 1 < len(dates) and pd.Timestamp(dates[i + 1]).weekday() == 1 else None
        if tuesday is None or friday is None:
            continue
        entry_i = cash_open(state, tuesday)
        flat = state["close_i"].get(friday)
        if entry_i is None or flat is None or flat <= entry_i:
            continue
        entry_px = float(state["open"][entry_i])
        book["down_monday_to_friday"].append(trade(tuesday, float(state["close"][flat] - entry_px), entry_px))
    for i, day in enumerate(dates):
        if day.month not in (1, 4, 7, 10):
            continue
        if i and dates[i - 1].month == day.month:
            continue
        entry_i = cash_open(state, day)
        if entry_i is None or i + 3 >= len(dates):
            continue
        flat = state["close_i"].get(dates[i + 3])
        if flat is None or flat <= entry_i:
            continue
        entry_px = float(state["open"][entry_i])
        book["quarter_open_hold3"].append(trade(day, float(state["close"][flat] - entry_px), entry_px))
    return book


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    print("DATA last USA500", usa.index[-1].isoformat(), flush=True)
    state = prepare_paths(usa)
    book = weekly_book(state)
    missing = [name for name in NEW_CELLS if name not in book]
    if missing:
        raise RuntimeError(str(missing))
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    test_end = max(stamp.date() for stamp in yahoo.index if stamp.date() <= date(2026, 11, 12))
    prior = old_tradebook(yahoo, symbol_paths("usa500")[0])
    prior.update(new_tradebook(yahoo, usa))
    prior.update(target_book(state))
    prior.update(window_book(state))
    prior.update(calendar_book(state))
    prior.update(trend_book(usa))
    prior.update(build_book(state, cross_asset(Path("/tmp/rare_data/daily")), state["close"]))
    prior.update(stop_book(state))
    prior.update(vwap_book(state))
    prior.update(lead_lag(usa, tech))
    prior.update(opening_fade(usa))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= test_end]
    names, cols, rows = [], [], []
    for name, trades in prior.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    for name in NEW_CELLS:
        trades = book[name]
        test = summarize(keep(trades, TEST_START, test_end), COST)
        stress = summarize(keep(trades, TEST_START, test_end), COST * 2)
        val = summarize(keep(trades, VAL_START, VAL_END), COST)
        train = summarize(keep(trades, TRAIN_START, TRAIN_END), COST)
        rows.append({
            "name": name,
            "test": test,
            "test_2x": slim(stress),
            "validation": slim(val),
            "train": slim(train),
            "validation_failed": fails_validation(val),
        })
        names.append(name)
        cols.append(pnl_on_days(trades, calendar, COST))
        print(name, "n", test["trades"], "win", test["win_rate"], test.get("win_rate_ci"), "exp", test["expectancy"], test["expectancy_ci"], "2x", stress["expectancy"], stress["expectancy_ci"], flush=True)
    mat = np.column_stack(cols)
    best = int(np.nanargmax(np.nan_to_num(mat.mean(0), nan=-1e9)))
    reality = whites_reality_check(mat, float(mat[:, best].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    dsr = deflated_sharpe_of(mat[:, best], sr_star)
    passed = []
    for row in rows:
        col = names.index(row["name"])
        own = whites_reality_check(mat, float(mat[:, col].mean()))
        own_dsr = deflated_sharpe_of(mat[:, col], sr_star)
        row["family_wise"] = {"reality_p": own["p_value"], "dsr": own_dsr["dsr"], "survives": bool(own["survives"] and own_dsr["survives"])}
        row["meets_success_bar"] = full_pass(row)
        if row["meets_success_bar"]:
            passed.append(row["name"])
    payload = {
        "preregistered": list(NEW_CELLS),
        "data_last_bar": usa.index[-1].isoformat(),
        "test_end": str(test_end),
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
    }
    Path("artifacts/rare_setups/run19.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "BEST", names[best], reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4), "N", len(names))


if __name__ == "__main__":
    main()
