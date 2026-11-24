"""Run 50. Fixed before any trade result is computed.

This is not a new rule. The BAA compression from round 48 stays as
published: the 20-day change in Moody's BAA minus the 10-year crosses
from positive to negative. Buy the next 09:30 ET. Sell the 15:55 close
ten sessions later.

The confirmatory sample is QQQ, IWM, DIA, and EFA on the 2022-2026
test, plus the same S&P rule on 2012-2017, which was not used to choose
it. A pass needs the 2022-2026 S&P bar, the pooled four-index bar, the
2012-2017 bar, and the reality check. One index is not picked afterward.

E-mini COT starts in February 2022, so it is not a separate history.
NFCI, STLFSI, oil, gold, the dollar, expiration week, and turn-of-month
are not repeated.
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
from rare_setups_run16 import TRAIN_END, TRAIN_START
from rare_setups_run17 import load_bars, summarize
from rare_setups_run18 import symbol_paths
from rare_setups_run25 import bar_clears, complete_sessions, fraction_book, keep, slim, weekday_bars
from rare_setups_run47 import build_spx as build47
from rare_setups_run47 import matrix_through_46, signals_for as signals47
from rare_setups_run48 import build_spx, signals_for
from rare_setups_run49 import build_spx as build49
from rare_setups_run49 import signals_for as signals49
from rare_setups_study import COST, build_daily, load_daily

RULE = "baa_compress_long"
HOLD = 10
MARKETS = ("QQQ", "IWM", "DIA", "EFA")
DAILY = Path("/tmp/rare_data/daily")


def index_book(stem: str, signal_days: list[date], last_day: date) -> list[dict]:
    frame = load_daily(DAILY, stem)
    close = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = close / frame["Close"].replace(0, np.nan)
    work = pd.DataFrame({"open": frame["Open"] * factor, "close": close}).dropna().sort_index()
    days = [stamp.date() for stamp in work.index if stamp.date() <= last_day]
    rows = []
    exit_day = date(1900, 1, 1)
    for signal_day in signal_days:
        entry_i = next((i for i, day in enumerate(days) if day > max(signal_day, exit_day) and (day - signal_day).days <= 4), None)
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
    print("PRE-REGISTERED", RULE, "markets", MARKETS, "early", TRAIN_START, TRAIN_END, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, flush=True)
    signals = signals_for()
    spx = build_spx(state, signals)[RULE]
    parts = {stem: index_book(stem, signals[RULE], last_day) for stem in MARKETS}
    pooled = [row for stem in MARKETS for row in parts[stem]]
    stress = summarize(keep(spx, TEST_START, last_day), COST * 2)
    early = summarize(keep(spx, TRAIN_START, TRAIN_END), COST * 2)
    markets = {}
    for stem, rows in parts.items():
        markets[stem] = slim(summarize(fraction_book(keep(rows, TEST_START, last_day), 0.0004), 0.0))
        print(stem, markets[stem]["trades"], markets[stem]["expectancy"], markets[stem]["expectancy_ci"], markets[stem]["profit_factor"], flush=True)
    pool = summarize(fraction_book(keep(pooled, TEST_START, last_day), 0.0004), 0.0)
    print("POOL", pool["trades"], pool["expectancy"], pool["expectancy_ci"], pool["profit_factor"], pool["years_positive"], flush=True)
    print("EARLY", early["trades"], early["expectancy"], early["expectancy_ci"], early["profit_factor"], early["years_positive"], flush=True)
    yahoo = build_daily(DAILY)[0]
    matrix = matrix_through_46(state, usa, tech, yahoo, tradable)
    matrix.update(build47(state, signals47(tradable)))
    matrix.update(build_spx(state, signals))
    matrix.update(build49(state, signals49(tradable)))
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
    passed = bool(bar_clears(stress) and bar_clears(pool) and bar_clears(early) and family["survives"])
    payload = {
        "preregistered": RULE,
        "markets": list(MARKETS),
        "early_window": [str(TRAIN_START), str(TRAIN_END)],
        "definition": "Same BAA 20-day compression. Pass needs the 2022-2026 S&P bar, the pooled QQQ/IWM/DIA/EFA bar, the 2012-2017 S&P bar, and the reality check.",
        "test_end": str(last_day),
        "spx_2x": slim(stress),
        "spx_bar": bar_clears(stress),
        "early_2x": slim(early),
        "early_bar": bar_clears(early),
        "by_market_2x": markets,
        "pooled_2x": slim(pool),
        "pooled_bar": bar_clears(pool),
        "family_wise": family,
        "matrix_rules": int(len(names)),
        "any_meets_success_bar": passed,
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run50.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", passed, "N", len(names), family)


if __name__ == "__main__":
    main()
