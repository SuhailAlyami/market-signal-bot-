"""Run 25. Fixed before any trade result is computed.

Runs 12 through 24 already tested put/call (the file stops in 2019),
VIX term structure, CFTC positioning, the Treasury curve, Fed liquidity,
NFCI, HYG/LQD reclaim, S&P member breadth, and the macro calendar.
Those are not repeated.

This family is a next-session lead. Another market has moved and the
S&P cash session has not. The proxy is known at its own close. Entry is
the next S&P session at 09:30 ET. Exit is the 15:55 close three sessions
later. One position per rule. Adjusted closes.

A day is quiet when the S&P session return is within 0.25% either way.
The impulse is 0.50% for every ratio and for TLT, and 0.30% for UUP.
Risk-on, the long, is HYG/IEF up, XLY/XLP up, XLU/XLK down, copper/gold
up (HG=F over GC=F), UUP down, and TLT down. The short is the opposite
impulse on a quiet S&P day.

Replication is QQQ, same signal dates, next open, same three-session
hold, with 0.04% subtracted as the doubled round-trip cost. The
reality-check matrix includes the earlier rules, including round 24.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import TRAIN_END, TRAIN_START, calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, stop_book, summarize, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_run19 import weekly_book
from rare_setups_run20 import build_signals, features as run20_features, next_session_after, open_map
from rare_setups_run21 import HOLDS as BREADTH_HOLDS
from rare_setups_run21 import NEW_CELLS as BREADTH_CELLS
from rare_setups_run21 import breadth_days
from rare_setups_study import COST, build_daily, load_daily

QUIET = 0.0025
HOLD = 3
DAILY = Path("/tmp/rare_data/daily")
SPECS = (
    ("hyg_ief", "HYG", "IEF", 1, 0.005),
    ("xly_xlp", "XLY", "XLP", 1, 0.005),
    ("xlu_xlk", "XLU", "XLK", -1, 0.005),
    ("cu_au", "HG_F", "GC_F", 1, 0.005),
    ("uup", "UUP", None, -1, 0.003),
    ("tlt", "TLT", None, -1, 0.005),
)
NEW_CELLS = tuple(name for stem, *_rest in SPECS for name in (f"{stem}_on_long", f"{stem}_off_short"))
SIDES = {name: (1 if name.endswith("_long") else -1) for name in NEW_CELLS}


def adjusted(frame: pd.DataFrame) -> pd.Series:
    for column in ("Adj close", "Adj Close", "Close"):
        if column in frame.columns:
            return frame[column]
    raise KeyError(frame.columns.tolist())


def proxy_return(left: str, right: str | None) -> pd.Series:
    base = adjusted(load_daily(DAILY, left))
    series = base if right is None else base / adjusted(load_daily(DAILY, right))
    series = series.sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series.pct_change()


def session_returns(state) -> dict[date, float]:
    found = {}
    previous = None
    for day in state["session_dates"]:
        close_i = state["close_i"].get(day)
        if close_i is None:
            continue
        price = float(state["close"][close_i])
        if previous not in (None, 0):
            found[day] = price / previous - 1
        previous = price
    return found


def weekday_bars(bars: pd.DataFrame) -> pd.DataFrame:
    """Drop Saturday and the frozen Sunday cash-hour prints. Keep Sunday 18:00, the real reopen."""
    minute = bars.index.hour * 60 + bars.index.minute
    saturday = bars.index.day_of_week == 5
    sunday_placeholder = (bars.index.day_of_week == 6) & (minute < 18 * 60)
    return bars[~(saturday | sunday_placeholder)]


def complete_sessions(state) -> list[date]:
    return [day for day in state["session_dates"] if day in state["close_i"] and day.weekday() < 5]


def signals_for(state, tradable: set[date]) -> dict[str, list[date]]:
    spx = session_returns(state)
    book = {name: [] for name in NEW_CELLS}
    for stem, left, right, risk_sign, impulse in SPECS:
        change = proxy_return(left, right)
        for stamp, value in change.dropna().items():
            day = stamp.date()
            if day not in tradable or day not in spx or abs(spx[day]) > QUIET:
                continue
            appetite = risk_sign * float(value)
            if appetite >= impulse:
                book[f"{stem}_on_long"].append(day)
            elif appetite <= -impulse:
                book[f"{stem}_off_short"].append(day)
    return book


def trade_row(day: date, gross: float, entry: float, side: int) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": side, "entry": float(entry)}


def build_spx(state, signals) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for signal_day in signals[name]:
            entry_day = next_session_after(state["session_dates"], max(signal_day, exit_day))
            if entry_day is None or entry_day <= exit_day:
                continue
            pos = state["pos"].get(entry_day)
            entry_i = opens.get(entry_day)
            if pos is None or entry_i is None or pos + HOLD >= len(state["session_dates"]):
                continue
            exit_day = state["session_dates"][pos + HOLD]
            exit_i = state["close_i"].get(exit_day)
            if exit_i is None or exit_i <= entry_i or exit_day not in state["close_i"]:
                continue
            entry_px = float(state["open"][entry_i])
            exit_px = float(state["close"][exit_i])
            book[name].append(trade_row(entry_day, side * (exit_px - entry_px), entry_px, side))
    return book


def qqq_frame() -> pd.DataFrame:
    frame = load_daily(DAILY, "QQQ")
    close = adjusted(frame)
    factor = close / frame["Close"].replace(0, np.nan)
    out = pd.DataFrame({"open": frame["Open"] * factor, "close": close}, index=frame.index)
    return out.dropna().sort_index()


def build_qqq(frame: pd.DataFrame, signals, last_day: date) -> dict[str, list[dict]]:
    days = [stamp.date() for stamp in frame.index if stamp.date() <= last_day]
    frame = frame.loc[[stamp for stamp in frame.index if stamp.date() <= last_day]]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for signal_day in signals[name]:
            entry_i = next((i for i, day in enumerate(days) if day > max(signal_day, exit_day)), None)
            if entry_i is None or entry_i + HOLD >= len(days):
                continue
            exit_i = entry_i + HOLD
            entry_px = float(frame["open"].iloc[entry_i])
            exit_px = float(frame["close"].iloc[exit_i])
            if entry_px <= 0:
                continue
            book[name].append(trade_row(days[entry_i], side * (exit_px - entry_px) / entry_px, entry_px, side))
            exit_day = days[exit_i]
    return book


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def bar_clears(stats: dict) -> bool:
    ci = stats.get("expectancy_ci") or [None, None]
    pf = stats.get("profit_factor")
    pf_ok = pf > 1.5 if pf is not None else stats.get("avg_loss") is None and (stats.get("expectancy") or 0) > 0
    return bool(
        (stats.get("trades") or 0) >= 15
        and ci[0] is not None and ci[0] > 0
        and pf_ok
        and (stats.get("years_positive") or 0) > 0.60
    )


def slim(row: dict) -> dict:
    keys = ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss", "years_positive", "years")
    return {key: row.get(key) for key in keys}


def fraction_book(trades, fraction: float):
    return [{**row, "gross": row["gross"] - fraction} for row in trades]


def prior_books(state, usa, tech, yahoo):
    import rare_setups_run20 as r20
    import rare_setups_run22 as r22
    import rare_setups_run24 as r24

    cells, holds = r20.NEW_CELLS, dict(r20.HOLDS)
    earlier = run20_features()
    earlier.pop("_ranges")
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    prior20 = build_signals(state, earlier)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    r20.NEW_CELLS, r20.HOLDS = BREADTH_CELLS, BREADTH_HOLDS
    prior21 = build_signals(state, breadth_days(panel))
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    weekly = r24.net_liquidity()
    old = r24.liquidity_signals(weekly)
    old["nfci_rollover_long"] = r24.nfci_signals(r24.fred_series("NFCI"))
    old.update(r24.credit_signals())
    prior24 = r24.build_spx(state, old)
    matrix = old_tradebook(yahoo, symbol_paths("usa500")[0])
    matrix.update(new_tradebook(yahoo, usa))
    matrix.update(target_book(state))
    matrix.update(window_book(state))
    matrix.update(calendar_book(state))
    matrix.update(trend_book(usa))
    matrix.update(build_book(state, cross_asset(DAILY), state["close"]))
    matrix.update(stop_book(state))
    matrix.update(vwap_book(state))
    matrix.update(lead_lag(usa, tech))
    matrix.update(opening_fade(usa))
    matrix.update(weekly_book(state))
    matrix.update(prior20)
    matrix.update(prior21)
    matrix.update(r22.build(state, r22.calendars(state["session_dates"])))
    matrix.update(prior24)
    return matrix


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS), flush=True)
    for name in NEW_CELLS:
        print(" -", name, "side", SIDES[name], "hold", HOLD, flush=True)
    usa = weekday_bars(load_bars(symbol_paths("usa500")))
    tech = weekday_bars(load_bars(symbol_paths("usatech")))
    state = prepare_paths(usa)
    tradable = complete_sessions(state)
    last_day = tradable[-1]
    print("LAST_COMPLETE", last_day, "sessions", len(tradable), flush=True)
    signals = signals_for(state, set(tradable))
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    book = build_spx(state, signals)
    qqq = build_qqq(qqq_frame(), signals, last_day)
    print("prior family", flush=True)
    yahoo = build_daily(DAILY)[0]
    test_end = last_day
    matrix = prior_books(state, usa, tech, yahoo)
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= test_end]
    names, cols, rows = [], [], []
    for name, trades in matrix.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        test = summarize(keep(book[name], TEST_START, test_end), COST)
        stress = summarize(keep(book[name], TEST_START, test_end), COST * 2)
        val = summarize(keep(book[name], VAL_START, VAL_END), COST)
        train = summarize(keep(book[name], TRAIN_START, TRAIN_END), COST)
        rep = summarize(fraction_book(keep(qqq[name], TEST_START, test_end), 0.0004), 0.0)
        row = {
            "name": name,
            "side": "short" if SIDES[name] < 0 else "long",
            "entry": "next session 09:30 ET",
            "exit": "15:55 ET, 3 cash sessions later",
            "test": test,
            "test_2x": slim(stress),
            "validation": slim(val),
            "train": slim(train),
            "replication_qqq_2x": slim(rep),
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
            "qqq", rep["trades"], rep["expectancy"], rep["expectancy_ci"],
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
        "definition": "Quiet S&P day is a session return inside +/-0.25%. Impulse is 0.50%, or 0.30% for UUP. Entry is the next 09:30. Exit is 3 sessions later. Adjusted closes.",
        "not_retested": "Put/call, VIX term structure, COT, Treasury curve, Fed liquidity, NFCI, HYG/LQD reclaim, member breadth, FOMC, expiry, turn-of-month.",
        "test_end": str(test_end),
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
    Path("artifacts/rare_setups/run25.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


if __name__ == "__main__":
    main()
