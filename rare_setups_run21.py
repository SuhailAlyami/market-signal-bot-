"""Run 21. Fixed before the breadth panel is scored.

Breadth is the share of current S&P 500 members, from Yahoo adjusted
closes. The list is today's membership, not the historical one, so a
stock that joined late is missing from earlier years and a stock that
left is missing entirely. That bias is recorded and is not ignored.

1. breadth_90down_90up. A session where at least 90% of the members
   that traded closed down, followed within three sessions by a session
   where at least 90% closed up. Enter 18:00 on the up session. Exit
   five cash sessions later. A 90% down day followed by a 90% up day is
   the classic selling climax then demand thrust.
2. zweig_thrust. The 10-session EMA of advances/(advances+declines)
   crosses above 0.615, and the lowest reading of that EMA in the prior
   10 sessions was below 0.40. Enter 18:00. Exit ten cash sessions later.
3. above50_thrust. The share of members above their own 50-session
   average crosses above 0.45 after having been below 0.15 at some point
   in the prior 10 sessions. Enter 18:00. Exit ten cash sessions later.

A day counts only when at least 400 members have a price. One position
per rule. Time exits only. Replication is the same dates on USATECH.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, stop_book, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_run19 import weekly_book
from rare_setups_run20 import (
    VAL_END,
    VAL_START,
    bar_clears,
    build_signals,
    features as prior_features,
    net_of_fraction,
    slim,
    summarize,
)
from rare_setups_study import COST, build_daily

NEW_CELLS = ("breadth_90down_90up", "zweig_thrust", "above50_thrust")
HOLDS = {"breadth_90down_90up": 5, "zweig_thrust": 10, "above50_thrust": 10}


def breadth_days(panel: pd.DataFrame) -> dict[str, list[date]]:
    close = panel.sort_index()
    both = close.notna() & close.shift(1).notna()
    up = ((close > close.shift(1)) & both).sum(axis=1)
    down = ((close < close.shift(1)) & both).sum(axis=1)
    present = both.sum(axis=1)
    enough = present >= 400
    adv_share = up / (up + down).replace(0, np.nan)
    down90 = enough & (adv_share <= 0.10)
    up90 = enough & (adv_share >= 0.90)
    follow = []
    down_pos = [i for i, flag in enumerate(down90.to_numpy()) if flag]
    index = close.index
    down_set = set(down_pos)
    for i, flag in enumerate(up90.to_numpy()):
        if not flag:
            continue
        if any((i - gap) in down_set for gap in (1, 2, 3)):
            follow.append(index[i].date())
    ema = adv_share.ewm(span=10, adjust=False).mean()
    thrust = []
    values = ema.to_numpy()
    for i in range(11, len(values)):
        window = values[i - 10:i]
        if np.isfinite(values[i]) and values[i] > 0.615 and values[i - 1] <= 0.615 and np.nanmin(window) < 0.40 and enough.iloc[i]:
            thrust.append(index[i].date())
    ma = close.rolling(50).mean()
    usable = close.notna() & ma.notna()
    share = ((close > ma) & usable).sum(axis=1) / usable.sum(axis=1).replace(0, np.nan)
    above = []
    share_values = share.to_numpy()
    for i in range(11, len(share_values)):
        window = share_values[i - 10:i]
        if usable.sum(axis=1).iloc[i] < 400:
            continue
        if np.isfinite(share_values[i]) and share_values[i] > 0.45 and share_values[i - 1] <= 0.45 and np.nanmin(window) < 0.15:
            above.append(index[i].date())
    return {
        "breadth_90down_90up": follow,
        "zweig_thrust": thrust,
        "above50_thrust": above,
    }


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, "hold", HOLDS[name], flush=True)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    print("BREADTH", panel.shape, str(panel.index.min().date()), str(panel.index.max().date()), flush=True)
    import rare_setups_run20 as prior
    original_cells, original_holds = prior.NEW_CELLS, dict(prior.HOLDS)
    signal_days = breadth_days(panel)
    for name in NEW_CELLS:
        print(" signals", name, len(signal_days[name]), flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    state = prepare_paths(usa)
    prior.NEW_CELLS = NEW_CELLS
    prior.HOLDS = HOLDS
    book = build_signals(state, signal_days)
    tech_book = build_signals(prepare_paths(tech), signal_days)
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    test_end = max(stamp.date() for stamp in yahoo.index if stamp.date() <= date(2026, 11, 12))
    earlier = prior_features()
    earlier.pop("_ranges")
    prior.NEW_CELLS = original_cells
    prior.HOLDS = original_holds
    prior_book = build_signals(state, earlier)
    matrix_prior = old_tradebook(yahoo, symbol_paths("usa500")[0])
    matrix_prior.update(new_tradebook(yahoo, usa))
    matrix_prior.update(target_book(state))
    matrix_prior.update(window_book(state))
    matrix_prior.update(calendar_book(state))
    matrix_prior.update(trend_book(usa))
    matrix_prior.update(build_book(state, cross_asset(Path("/tmp/rare_data/daily")), state["close"]))
    matrix_prior.update(stop_book(state))
    matrix_prior.update(vwap_book(state))
    matrix_prior.update(lead_lag(usa, tech))
    matrix_prior.update(opening_fade(usa))
    matrix_prior.update(weekly_book(state))
    matrix_prior.update(prior_book)
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= test_end]
    names, cols, rows = [], [], []
    for name, trades in matrix_prior.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        trades = book[name]
        test = summarize(keep_window(trades, TEST_START, test_end), COST)
        stress = summarize(keep_window(trades, TEST_START, test_end), COST * 2)
        rep = summarize(net_of_fraction(keep_window(tech_book[name], TEST_START, test_end), 0.0004), 0.0)
        row = {
            "name": name,
            "entry": "18:00 ET",
            "exit": f"15:55 ET close {HOLDS[name]} cash sessions later",
            "test": test,
            "test_2x": slim(stress),
            "replication_usatech_2x": slim(rep),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep),
        }
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(trades, calendar, COST))
        print(name, "n", test["trades"], "win", test["win_rate"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], "rep", rep["trades"], rep["expectancy"], flush=True)
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
        "membership_limit": "Current Wikipedia S&P 500 members only. Departed members are absent and recent additions have a short history. This is not a point-in-time universe.",
        "breadth_shape": [int(panel.shape[0]), int(panel.shape[1])],
        "breadth_end": str(panel.index.max().date()),
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
    Path("artifacts/rare_setups/run21.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


def keep_window(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


if __name__ == "__main__":
    main()
