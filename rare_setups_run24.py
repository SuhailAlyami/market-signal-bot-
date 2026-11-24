"""Run 24. Fixed before any trade result is computed.

Net liquidity is WALCL minus overnight reverse repo minus the Treasury
general account, in billions. WALCL and WTREGEN are millions in the
FRED files and are divided by 1000. RRPONTSYD is already in billions.
The Wednesday H.4.1 observation is public Thursday at 16:30 ET, so the
entry is the Friday cash open, or the next session if Friday is shut.
NFCI is dated Friday and is public the following Wednesday at 08:30 ET,
so the entry is that Wednesday's cash open.

Rules:
1. liq_4w_up_long. The 4-week change in net liquidity crosses from
   negative to positive. Enter Friday 09:30. Exit 20 cash sessions later.
2. liq_4w_down_short. The 4-week change crosses from positive to
   negative. Same clock, short.
3. liq_z13_turn_long. The 13-week z-score, using only the prior 13
   weeks, was below -1.5 last week and is higher this week. Same clock.
4. nfci_rollover_long. NFCI fell this week after rising last week, and
   last week's level is at or above the median of the prior 52 weeks.
   Enter Wednesday 09:30. Exit 20 cash sessions later.
5. hyg_lqd_reclaim_long. Yesterday's HYG/LQD adjusted-close ratio was a
   20-day low and today's ratio closed back above it. Enter 18:00 ET.
   Exit five cash sessions later. BAMLH0A0HYM2 starts in November 2023,
   so it is not this rule.
6. hyg_lqd_break_short. Yesterday was a 20-day high and today closed
   back below it. Same clock, short.

One position per rule. Time exits only. Replication is the same signal
dates on IWM, entering at the cash open on the entry date, or at the
next open when the S&P entry was 18:00. IWM cost is 0.02% of price each
way. A pass needs the S&P 2x bar, the IWM 2x bar, and the reality check
across every rule tested so far.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import TRAIN_END, TRAIN_START, calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, stop_book, summarize, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_run19 import weekly_book
from rare_setups_run20 import build_signals, features as run20_features, open_map
from rare_setups_run21 import NEW_CELLS as BREADTH_CELLS
from rare_setups_run21 import HOLDS as BREADTH_HOLDS
from rare_setups_run21 import breadth_days
from rare_setups_study import COST, build_daily, load_daily

FRED = Path("data/fred")
NEW_CELLS = (
    "liq_4w_up_long",
    "liq_4w_down_short",
    "liq_z13_turn_long",
    "nfci_rollover_long",
    "hyg_lqd_reclaim_long",
    "hyg_lqd_break_short",
)
HOLDS = {
    "liq_4w_up_long": 20,
    "liq_4w_down_short": 20,
    "liq_z13_turn_long": 20,
    "nfci_rollover_long": 20,
    "hyg_lqd_reclaim_long": 5,
    "hyg_lqd_break_short": 5,
}
SIDES = {
    "liq_4w_up_long": 1,
    "liq_4w_down_short": -1,
    "liq_z13_turn_long": 1,
    "nfci_rollover_long": 1,
    "hyg_lqd_reclaim_long": 1,
    "hyg_lqd_break_short": -1,
}


def fred_series(name: str) -> pd.Series:
    frame = pd.read_csv(FRED / f"{name}.csv", parse_dates=["observation_date"])
    series = pd.to_numeric(frame[name], errors="coerce")
    series.index = pd.to_datetime(frame["observation_date"]).dt.normalize()
    return series.sort_index()


def first_on_or_after(days: list[date], day: date) -> date | None:
    for item in days:
        if item >= day:
            return item
    return None


def net_liquidity() -> pd.DataFrame:
    walcl = fred_series("WALCL") / 1000.0
    tga = fred_series("WTREGEN") / 1000.0
    rrp = fred_series("RRPONTSYD").dropna()
    weekly = pd.concat({"walcl": walcl, "tga": tga}, axis=1).dropna()
    rrp_asof = rrp.reindex(weekly.index.union(rrp.index)).sort_index().ffill()
    weekly["rrp"] = rrp_asof.reindex(weekly.index)
    weekly["nl"] = weekly["walcl"] - weekly["rrp"] - weekly["tga"]
    weekly = weekly.dropna(subset=["nl"])
    weekly["chg4"] = weekly["nl"] - weekly["nl"].shift(4)
    history = weekly["nl"].shift(1)
    mean = history.rolling(13).mean()
    std = history.rolling(13).std(ddof=1)
    weekly["z13"] = (weekly["nl"] - mean) / std.replace(0, np.nan)
    return weekly


def liquidity_signals(weekly: pd.DataFrame) -> dict[str, list[date]]:
    up = (weekly["chg4"].shift(1) < 0) & (weekly["chg4"] > 0)
    down = (weekly["chg4"].shift(1) > 0) & (weekly["chg4"] < 0)
    turned = (weekly["z13"].shift(1) < -1.5) & (weekly["z13"] > weekly["z13"].shift(1))
    # Wednesday observation, public Thursday 16:30, tradable Friday.
    def fridays(mask: pd.Series) -> list[date]:
        found = []
        for stamp in weekly.index[mask.fillna(False)]:
            found.append((stamp + pd.Timedelta(days=2)).date())
        return found
    return {
        "liq_4w_up_long": fridays(up),
        "liq_4w_down_short": fridays(down),
        "liq_z13_turn_long": fridays(turned),
    }


def nfci_signals(nfci: pd.Series) -> list[date]:
    prior = nfci.shift(1)
    peak = (nfci < prior) & (prior > nfci.shift(2)) & (prior >= nfci.shift(2).rolling(52).median())
    found = []
    for stamp in nfci.index[peak.fillna(False)]:
        # Friday reference, public the next Wednesday 08:30.
        found.append((stamp + pd.Timedelta(days=5)).date())
    return found


def credit_signals() -> dict[str, list[date]]:
    hyg = load_daily(Path("/tmp/rare_data/daily"), "HYG")
    lqd = load_daily(Path("/tmp/rare_data/daily"), "LQD")
    def adjusted(frame: pd.DataFrame) -> pd.Series:
        for name in ("Adj Close", "Adj close", "Adjclose"):
            if name in frame.columns:
                return frame[name]
        return frame["Close"]
    hyg_px = adjusted(hyg)
    lqd_px = adjusted(lqd)
    ratio = (hyg_px / lqd_px).dropna().sort_index()
    ratio = ratio[~ratio.index.duplicated(keep="last")]
    yesterday = ratio.shift(1)
    low20 = ratio.rolling(20).min().shift(1)
    high20 = ratio.rolling(20).max().shift(1)
    reclaim = (yesterday <= low20) & (ratio > yesterday) & (yesterday < ratio.shift(2))
    breakdown = (yesterday >= high20) & (ratio < yesterday) & (yesterday > ratio.shift(2))
    return {
        "hyg_lqd_reclaim_long": [stamp.date() for stamp in ratio.index[reclaim.fillna(False)]],
        "hyg_lqd_break_short": [stamp.date() for stamp in ratio.index[breakdown.fillna(False)]],
    }


def trade_row(day: date, gross: float, entry: float, side: int) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": side, "entry": float(entry)}


def fill_open(state, entry_day: date, ahead: int, side: int, opens: dict[date, int]):
    day = first_on_or_after(state["session_dates"], entry_day)
    if day is None:
        return None
    pos = state["pos"].get(day)
    entry_i = opens.get(day)
    if pos is None or entry_i is None or pos + ahead >= len(state["session_dates"]):
        return None
    exit_day = state["session_dates"][pos + ahead]
    exit_i = state["close_i"].get(exit_day)
    if exit_i is None or exit_i <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    exit_px = float(state["close"][exit_i])
    return trade_row(day, side * (exit_px - entry_px), entry_px, side), exit_day


def fill_1800(state, signal_day: date, ahead: int, side: int):
    known = state["close_i"].get(signal_day)
    pos = state["pos"].get(signal_day)
    if known is None or pos is None or pos + ahead >= len(state["session_dates"]):
        return None
    entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
    exit_day = state["session_dates"][pos + ahead]
    exit_i = state["close_i"].get(exit_day)
    if entry_ts is None or exit_i is None:
        return None
    entry_i = int(state["index"].searchsorted(entry_ts))
    if exit_i <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    exit_px = float(state["close"][exit_i])
    return trade_row(signal_day, side * (exit_px - entry_px), entry_px, side), exit_day


def build_spx(state, signals: dict[str, list[date]]) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for day in signals[name]:
            if day <= exit_day:
                continue
            if name.startswith("hyg_"):
                filled = fill_1800(state, day, HOLDS[name], side)
            else:
                filled = fill_open(state, day, HOLDS[name], side, opens)
            if filled is None:
                continue
            row, exit_day = filled
            book[name].append(row)
    return book


def iwm_frame() -> pd.DataFrame:
    frame = load_daily(Path("/tmp/rare_data/daily"), "IWM")
    adjusted = frame["Adj close"] if "Adj close" in frame.columns else frame["Close"]
    factor = adjusted / frame["Close"].replace(0, np.nan)
    out = pd.DataFrame({
        "open": frame["Open"] * factor,
        "high": frame["High"] * factor,
        "low": frame["Low"] * factor,
        "close": adjusted,
    }, index=frame.index)
    return out.dropna().sort_index()


def build_iwm(frame: pd.DataFrame, signals: dict[str, list[date]]) -> dict[str, list[dict]]:
    days = [stamp.date() for stamp in frame.index]
    book = {name: [] for name in NEW_CELLS}
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        side = SIDES[name]
        for raw_day in signals[name]:
            start = raw_day
            if name.startswith("hyg_"):
                start = raw_day + timedelta(days=1)
            entry_i = next((i for i, day in enumerate(days) if day >= start and day > exit_day), None)
            if entry_i is None or entry_i + HOLDS[name] >= len(days):
                continue
            exit_i = entry_i + HOLDS[name]
            entry_px = float(frame["open"].iloc[entry_i])
            exit_px = float(frame["close"].iloc[exit_i])
            if entry_px <= 0:
                continue
            gross = side * (exit_px - entry_px) / entry_px
            entry_day = days[entry_i]
            book[name].append(trade_row(entry_day, gross, entry_px, side))
            exit_day = days[exit_i]
    return book


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def bar_clears(stats: dict) -> bool:
    ci = stats.get("expectancy_ci") or [None, None]
    pf = stats.get("profit_factor")
    if pf is None:
        pf_ok = stats.get("avg_loss") is None and (stats.get("expectancy") or 0) > 0
    else:
        pf_ok = pf > 1.5
    return bool(
        (stats.get("trades") or 0) >= 15
        and ci[0] is not None and ci[0] > 0
        and pf_ok
        and (stats.get("years_positive") or 0) > 0.60
    )


def slim(row: dict) -> dict:
    return {key: row.get(key) for key in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss", "years_positive", "years")}


def fraction_book(trades: list[dict], fraction: float) -> list[dict]:
    out = []
    for row in trades:
        item = dict(row)
        item["gross"] = row["gross"] - fraction
        out.append(item)
    return out


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, "side", SIDES[name], "hold", HOLDS[name], flush=True)
    weekly = net_liquidity()
    signals = liquidity_signals(weekly)
    signals["nfci_rollover_long"] = nfci_signals(fred_series("NFCI"))
    signals.update(credit_signals())
    for name in NEW_CELLS:
        print(" signals", name, len(signals[name]), flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    state = prepare_paths(usa)
    book = build_spx(state, signals)
    iwm = build_iwm(iwm_frame(), signals)
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    test_end = max(stamp.date() for stamp in yahoo.index if stamp.date() <= date(2026, 11, 12))
    import rare_setups_run20 as r20
    import rare_setups_run22 as r22
    cells, holds = r20.NEW_CELLS, dict(r20.HOLDS)
    earlier = run20_features()
    earlier.pop("_ranges")
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    prior20 = build_signals(state, earlier)
    panel = pd.read_pickle("/tmp/rare_data/external/breadth/closes.pkl")
    breadth = breadth_days(panel)
    r20.NEW_CELLS, r20.HOLDS = BREADTH_CELLS, BREADTH_HOLDS
    prior21 = build_signals(state, breadth)
    r20.NEW_CELLS, r20.HOLDS = cells, holds
    calendar_days = r22.calendars(state["session_dates"])
    prior22 = r22.build(state, calendar_days)
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
    matrix.update(prior22)
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
        rep = summarize(fraction_book(keep(iwm[name], TEST_START, test_end), 0.0004), 0.0)
        row = {
            "name": name,
            "side": "short" if SIDES[name] < 0 else "long",
            "entry": "18:00 ET on the signal day" if name.startswith("hyg_") else ("Wednesday 09:30 ET" if name.startswith("nfci") else "Friday 09:30 ET"),
            "exit": f"15:55 ET, {HOLDS[name]} cash sessions later",
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
        print(name, "n", test["trades"], "win", test["win_rate"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], "iwm", rep["trades"], rep["expectancy"], flush=True)
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
        "units": "Net liquidity is billions: WALCL/1000 - RRPONTSYD - WTREGEN/1000. RRP is the last published print on or before the Wednesday H.4.1 date.",
        "lags": "H.4.1 Wednesday print is traded Friday 09:30. NFCI Friday print is traded the next Wednesday 09:30. HYG/LQD is traded at 18:00 the same day.",
        "baml": "BAMLH0A0HYM2 is stored but not a rule. It starts 2023-11-13.",
        "test_end": str(test_end),
        "liquidity_end": str(weekly.index.max().date()),
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
    Path("artifacts/rare_setups/run24.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "N", len(names), reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4))


if __name__ == "__main__":
    main()
