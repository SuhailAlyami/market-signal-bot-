"""Run 38. Fixed before any trade result is computed.

This is not a new search. The single closest cell from round 24 stays
exactly as published: the four-week change in net liquidity crosses from
negative to positive, buy Friday 09:30 ET, sell the 15:55 close 20
sessions later.

The new work is the confirmatory sample. The same Friday dates are
traded on QQQ, IWM, the DAX, and the Nikkei. A pass needs three things
together: the original S&P doubled-cost bar, the pooled four-index
sample after 0.04%, and the reality check on the existing S&P column.
One index is not chosen after seeing which one worked.

Turn-of-month, monthly and quarterly expiration, VIX9D/VIX/VIX3M, and
the XLU/XLK and XLY/XLP ratios were already tested and are not repeated.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, pnl_on_days
from rare_setups_run14 import prepare_paths
from rare_setups_run17 import load_bars, summarize
from rare_setups_run18 import symbol_paths
from rare_setups_run24 import build_spx as build24
from rare_setups_run24 import credit_signals, liquidity_signals, net_liquidity
from rare_setups_run25 import bar_clears, complete_sessions, fraction_book, keep, slim, weekday_bars
from rare_setups_run34 import matrix_through_33
from rare_setups_run35 import build_spx as build35
from rare_setups_run35 import signals_for as signals35
from rare_setups_run36 import build_spx as build36
from rare_setups_run36 import signals_for as signals36
from rare_setups_run37 import build_spx as build37
from rare_setups_run37 import signals_for as signals37
from rare_setups_study import COST, build_daily, load_daily

RULE = "liq_4w_up_long"
HOLD = 20
MARKETS = ("QQQ", "IWM", "GDAXI", "N225")
DAILY = Path("/tmp/rare_data/daily")


def index_book(stem: str, fridays: list[date], last_day: date) -> list[dict]:
    frame = load_daily(DAILY, stem)
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    rows = []
    exit_day = date(1900, 1, 1)
    for friday in fridays:
        entry_i = next((i for i, day in enumerate(days) if day >= friday and day > exit_day and (day - friday).days <= 4), None)
        if entry_i is None or entry_i + HOLD >= len(days):
            continue
        exit_i = entry_i + HOLD
        entry_px = float(work["open"].iloc[entry_i])
        exit_px = float(work["close"].iloc[exit_i])
        if entry_px <= 0:
            continue
        day = days[entry_i]
        rows.append({"day": day, "year": day.year, "gross": (exit_px - entry_px) / entry_px, "side": 1, "entry": entry_px, "market": stem})
        exit_day = days[exit_i]
    return rows


def main() -> None:
    print("PRE-REGISTERED", RULE, "markets", MARKETS, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    weekly = net_liquidity()
    signals = liquidity_signals(weekly)
    from rare_setups_run24 import fred_series, nfci_signals
    signals["nfci_rollover_long"] = nfci_signals(fred_series("NFCI"))
    signals.update(credit_signals())
    spx = build24(state, signals)[RULE]
    parts = {stem: index_book(stem, signals[RULE], last_day) for stem in MARKETS}
    pooled = [row for stem in MARKETS for row in parts[stem]]
    test = summarize(keep(spx, TEST_START, last_day), COST)
    stress = summarize(keep(spx, TEST_START, last_day), COST * 2)
    markets = {}
    for stem, rows in parts.items():
        markets[stem] = slim(summarize(fraction_book(keep(rows, TEST_START, last_day), 0.0004), 0.0))
        print(stem, markets[stem]["trades"], markets[stem]["expectancy"], markets[stem]["expectancy_ci"], markets[stem]["profit_factor"], flush=True)
    pool = summarize(fraction_book(keep(pooled, TEST_START, last_day), 0.0004), 0.0)
    print("POOL", pool["trades"], pool["expectancy"], pool["expectancy_ci"], pool["profit_factor"], pool["years_positive"], flush=True)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_33(state, usa, tech, yahoo, tradable)
    from rare_setups_run34 import build_spx as build34
    from rare_setups_run34 import signals_for as signals34
    matrix.update(build34(state, signals34()))
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    matrix.update(build35(state, signals35(panel)))
    matrix.update(build36(state, signals36(tradable)))
    matrix.update(build37(state, signals37()))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= last_day]
    names, cols = [], []
    for name, trades in matrix.items():
        names.append(name)
        cols.append(pnl_on_days(trades, calendar, COST))
    mat = np.column_stack(cols)
    col = names.index(RULE)
    own = whites_reality_check(mat, float(mat[:, col].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    own_dsr = deflated_sharpe_of(mat[:, col], sr_star)
    family = {"reality_p": own["p_value"], "dsr": own_dsr["dsr"], "survives": bool(own["survives"] and own_dsr["survives"])}
    passed = bool(bar_clears(stress) and bar_clears(pool) and family["survives"])
    payload = {
        "preregistered": RULE,
        "markets": list(MARKETS),
        "definition": "Same four-week liquidity upturn. Friday 09:30, exit 20 sessions later. Pass needs the S&P bar, the pooled QQQ/IWM/DAX/Nikkei bar, and the existing reality check.",
        "not_retested": "Turn-of-month, expiration weeks, VIX9D/VIX/VIX3M, XLU/XLK, XLY/XLP.",
        "test_end": str(last_day),
        "spx_2x": slim(stress),
        "spx_bar": bar_clears(stress),
        "by_market_2x": markets,
        "pooled_2x": slim(pool),
        "pooled_bar": bar_clears(pool),
        "family_wise": family,
        "matrix_rules": int(len(names)),
        "any_meets_success_bar": passed,
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run38.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", passed, "N", len(names), family)


if __name__ == "__main__":
    main()
