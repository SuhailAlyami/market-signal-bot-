"""Run 15. The lists below are the whole new family. They are fixed
before any result is computed. Do not append to them after a run.

Standalone triggers fire at the cash close and buy the 18:00 ET reopen,
exiting at the next 16:00 close. Filters keep a prior signal (five lower
closes, RSI(2)<5, or four lower lows) only when the cross-asset condition
is true that same close. Filtered exits are the next cash close, a +0.3%
target within 3 sessions, or a +0.5% target within 3 sessions.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_END, TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp, load_5m
from rare_setups_run14 import gap_and_or_trades, prepare_paths, target_trades, vix_trades
from rare_setups_study import COST, build_daily, load_daily, metrics

NY = ZoneInfo("America/New_York")
SECTORS = ("XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE", "XLC")
BASES = ("consec5", "rsi2_lt5", "lower_lows_4")
EXITS = ("next_1600", "t0.003_d3", "t0.005_d3")
FILTERS = ("rsp_holds", "sector_above50", "credit_holds", "iwm_relative")
STANDALONE = (
    "rsp_holds_on_spx_down",
    "sectors_up_on_down_day",
    "sector_ma20_washout",
    "credit_hyg_lqd_holds",
    "flight_tlt_reversal",
    "flight_gld_reversal",
    "iwm_divergence",
)
FILTER_CELLS = tuple(f"{base}__18:00__{exit_name}__{filt}" for base in BASES for exit_name in EXITS for filt in FILTERS)
NEW_CELLS = STANDALONE + FILTER_CELLS


def day_ci(trades: list[dict], cost: float):
    if len(trades) < 2:
        return None
    grouped: dict[date, list[float]] = {}
    for row in trades:
        grouped.setdefault(row["day"], []).append(row["gross"] - cost)
    keys = list(grouped)
    if len(keys) < 2:
        return None
    rng = np.random.default_rng(16)
    samples = []
    for _ in range(400):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        pool = [value for i in pick for value in grouped[keys[i]]]
        if pool:
            samples.append(float(np.mean(pool)))
    if len(samples) < 20:
        return None
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def summarize(trades, cost):
    row = metrics(trades, cost)
    row["expectancy_ci"] = day_ci(trades, cost)
    row["trades_per_year"] = round(row["trades"] / 5, 3) if row["trades"] else 0
    return row


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def load_close(folder: Path, stem: str) -> pd.Series:
    path = folder / f"{stem}.csv"
    if not path.exists():
        return pd.Series(dtype=float)
    frame = load_daily(folder, stem)
    series = frame["Close"].copy()
    series.index = pd.to_datetime(series.index).tz_localize(None).normalize()
    return series.sort_index()


def cross_asset(folder: Path) -> pd.DataFrame:
    spy = load_close(folder, "SPY")
    frame = pd.DataFrame(index=spy.index)
    frame["spy"] = spy
    frame["rsp"] = load_close(folder, "RSP").reindex(frame.index)
    frame["iwm"] = load_close(folder, "IWM").reindex(frame.index)
    frame["hyg"] = load_close(folder, "HYG").reindex(frame.index)
    frame["lqd"] = load_close(folder, "LQD").reindex(frame.index)
    frame["tlt"] = load_close(folder, "TLT").reindex(frame.index)
    frame["gld"] = load_close(folder, "GLD").reindex(frame.index)
    sector_up = []
    sector_above = []
    for name in SECTORS:
        close = load_close(folder, name).reindex(frame.index)
        sector_up.append(close.pct_change() > 0)
        sector_above.append(close > close.rolling(50).mean())
    up = pd.concat(sector_up, axis=1)
    above = pd.concat(sector_above, axis=1)
    present_up = up.notna().sum(axis=1)
    present_above = above.notna().sum(axis=1)
    frame["sector_up_share"] = up.sum(axis=1) / present_up.where(present_up >= 8)
    frame["sector_above50"] = above.sum(axis=1) / present_above.where(present_above >= 8)
    # 20-day washout uses a shorter average and the same presence rule.
    above20 = []
    for name in SECTORS:
        close = load_close(folder, name).reindex(frame.index)
        above20.append(close > close.rolling(20).mean())
    above20 = pd.concat(above20, axis=1)
    present20 = above20.notna().sum(axis=1)
    frame["sector_above20"] = above20.sum(axis=1) / present20.where(present20 >= 8)
    frame["rsp_rel"] = frame["rsp"].pct_change() - frame["spy"].pct_change()
    frame["iwm_rel"] = frame["iwm"].pct_change() - frame["spy"].pct_change()
    ratio = frame["hyg"] / frame["lqd"]
    frame["credit_up"] = ratio.pct_change() >= 0
    frame["tlt_ret"] = frame["tlt"].pct_change()
    frame["gld_ret"] = frame["gld"].pct_change()
    return frame


def as_of(series: pd.Series, day: date):
    stamp = pd.Timestamp(day)
    if stamp not in series.index:
        return np.nan
    value = series.loc[stamp]
    return float(value) if np.isscalar(value) else np.nan


def build_book(state, cross: pd.DataFrame, spx: pd.Series) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    index = state["index"]
    for signal, side in state["flags"].items():
        for stamp in side.index[side.fillna(False)]:
            day = stamp.date()
            known = state["close_i"].get(day)
            if known is None:
                continue
            entry_ts = entry_stamp("18:00", index[known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
            if entry_ts is None:
                continue
            entry_i = int(index.searchsorted(entry_ts))
            entry_px = float(state["open"][entry_i])
            deadline = None
            pos = state["pos"].get(day)
            if pos is not None and pos + 1 < len(state["session_dates"]):
                deadline = state["close_i"].get(state["session_dates"][pos + 1])
            far = None
            if pos is not None and pos + 3 < len(state["session_dates"]):
                far = state["close_i"].get(state["session_dates"][pos + 3])
            if deadline is None or deadline <= entry_i:
                continue
            next_close = float(state["close"][deadline])
            gross_close = next_close - entry_px
            gross_03 = path_target(state, entry_i, entry_px, 0.003, far) if far and far > entry_i else None
            gross_05 = path_target(state, entry_i, entry_px, 0.005, far) if far and far > entry_i else None
            filters = {
                "rsp_holds": as_of(cross["rsp_rel"], day) > 0,
                "sector_above50": as_of(cross["sector_above50"], day) >= 0.5,
                "credit_holds": as_of(cross["credit_up"].astype(float), day) == 1,
                "iwm_relative": as_of(cross["iwm_rel"], day) > 0,
            }
            for filt, ok in filters.items():
                if not ok:
                    continue
                book[f"{signal}__18:00__next_1600__{filt}"].append(trade(day, gross_close))
                if gross_03 is not None:
                    book[f"{signal}__18:00__t0.003_d3__{filt}"].append(trade(day, gross_03))
                if gross_05 is not None:
                    book[f"{signal}__18:00__t0.005_d3__{filt}"].append(trade(day, gross_05))
    # Standalone triggers use the same USA500 session close.
    for i, day in enumerate(state["session_dates"][1:], start=1):
        prev = state["session_dates"][i - 1]
        close_i = state["close_i"].get(day)
        prev_i = state["close_i"].get(prev)
        if close_i is None or prev_i is None:
            continue
        spx_ret = state["close"][close_i] / state["close"][prev_i] - 1
        known_at = index[close_i] + pd.Timedelta(minutes=5)
        entry_ts = entry_stamp("18:00", known_at, state["clocks"], state["bars"])
        pos = state["pos"].get(day)
        if entry_ts is None or pos is None or pos + 1 >= len(state["session_dates"]):
            continue
        nxt = state["close_i"].get(state["session_dates"][pos + 1])
        if nxt is None:
            continue
        entry_i = int(index.searchsorted(entry_ts))
        gross = float(state["close"][nxt] - state["open"][entry_i])
        down = spx_ret < 0
        down_half = spx_ret <= -0.005
        down_one = spx_ret <= -0.01
        if down and as_of(cross["rsp_rel"], day) > 0:
            book["rsp_holds_on_spx_down"].append(trade(day, gross))
        if down and as_of(cross["sector_up_share"], day) >= 6 / 11:
            book["sectors_up_on_down_day"].append(trade(day, gross))
        if down and as_of(cross["sector_above20"], day) <= 0.20:
            book["sector_ma20_washout"].append(trade(day, gross))
        if down_half and as_of(cross["credit_up"].astype(float), day) == 1:
            book["credit_hyg_lqd_holds"].append(trade(day, gross))
        if down_one and as_of(cross["tlt_ret"], day) >= 0.005:
            book["flight_tlt_reversal"].append(trade(day, gross))
        if down_one and as_of(cross["gld_ret"], day) >= 0.005:
            book["flight_gld_reversal"].append(trade(day, gross))
        if down and as_of(cross["iwm_rel"], day) >= 0.003:
            book["iwm_divergence"].append(trade(day, gross))
    return book


def trade(day: date, gross: float) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": 1}


def path_target(state, entry_i: int, entry_px: float, target: float, deadline: int) -> float:
    level = entry_px * (1 + target)
    for j in range(entry_i, deadline + 1):
        if state["open"][j] >= level:
            return float(state["open"][j] - entry_px)
        if state["high"][j] >= level:
            return float(level - entry_px)
    return float(state["close"][deadline] - entry_px)


def day_ci(trades, cost):
    if len(trades) < 2:
        return None
    grouped: dict[date, list[float]] = {}
    for row in trades:
        grouped.setdefault(row["day"], []).append(row["gross"] - cost)
    keys = list(grouped)
    if len(keys) < 2:
        return None
    rng = np.random.default_rng(16)
    samples = []
    for _ in range(400):
        chosen = rng.choice(len(keys), size=len(keys), replace=True)
        pool = [value for i in chosen for value in grouped[keys[i]]]
        if pool:
            samples.append(float(np.mean(pool)))
    if len(samples) < 20:
        return None
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def summarize(trades, cost):
    from rare_setups_study import metrics
    row = metrics(trades, cost)
    row["expectancy_ci"] = day_ci(trades, cost)
    row["trades_per_year"] = round(row["trades"] / 5, 3) if row["trades"] else 0
    return row


def clearly_fails_validation(val: dict) -> bool:
    if val.get("trades", 0) < 10:
        return False
    ci = val.get("expectancy_ci") or [None, None]
    return ci[1] is not None and ci[1] < 0


def success(row) -> bool:
    test = row["test"]
    stress = row["test_2x"]
    wr = test.get("win_rate")
    wci = test.get("win_rate_ci") or [None, None]
    ci = test.get("expectancy_ci") or [None, None]
    ci2 = stress.get("expectancy_ci") or [None, None]
    return bool(
        test.get("trades", 0) >= 20
        and wr is not None and wr >= 0.70
        and wci[0] is not None and wci[0] > 0.50
        and ci[0] is not None and ci[0] > 0
        and ci2[0] is not None and ci2[0] > 0
        and row["family_wise"]["survives"]
        and not row["validation_failed"]
    )


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    path = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))[0]
    bars = load_5m(path)
    from rare_setups_run14 import prepare_paths
    state = prepare_paths(bars)
    state["clocks"] = __import__("rare_setups_run13", fromlist=["clock_index"]).clock_index(bars.index)
    state["bars"] = bars
    cross = cross_asset(Path("/tmp/rare_data/daily"))
    book = build_book(state, cross, state["close"])
    missing = [name for name in NEW_CELLS if name not in book]
    if missing:
        raise RuntimeError(str(missing))
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    prior = old_tradebook(yahoo, path)
    prior.update(new_tradebook(yahoo, bars))
    prior.update(target_book(state))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= TEST_END]
    names, cols, rows = [], [], []
    for name, trades in prior.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    for name in NEW_CELLS:
        trades = book[name]
        test = keep(trades, TEST_START, TEST_END)
        val = keep(trades, VAL_START, VAL_END)
        base = summarize(test, COST)
        stress = summarize(test, COST * 2)
        val_m = summarize(val, COST)
        rows.append({
            "name": name,
            "test": base,
            "test_2x": {"expectancy": stress["expectancy"], "expectancy_ci": stress["expectancy_ci"], "win_rate": stress["win_rate"], "profit_factor": stress["profit_factor"]},
            "validation": {k: val_m[k] for k in ("trades", "win_rate", "expectancy", "expectancy_ci", "profit_factor")},
            "validation_failed": clearly_fails_validation(val_m),
        })
        names.append(name)
        cols.append(pnl_on_days(trades, calendar, COST))
        print(name, "n", base["trades"], "win", base["win_rate"], base.get("win_rate_ci"), "exp", base["expectancy"], base["expectancy_ci"], flush=True)
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
        row["meets_success_bar"] = success(row)
        if row["meets_success_bar"]:
            passed.append(row["name"])
    availability = {
        "RSP_SPY_IWM_TLT_GLD_LQD": "Yahoo daily from 2005-01-03",
        "HYG": "Yahoo daily from 2007-04-11",
        "XLRE": "Yahoo daily from 2015-10-08",
        "XLC": "Yahoo daily from 2018-06-19",
        "breadth_rule": "A breadth day counts only when at least 8 of the 11 SPDRs have a price. XLC is missing before mid-2018 and XLRE before Oct 2015.",
        "path": "USA500 5-minute bid from 2011-09-18. Entry 18:00 ET, about 02:00 Riyadh in winter and 01:00 Riyadh in summer.",
    }
    payload = {
        "preregistered": list(NEW_CELLS),
        "new_cells": len(NEW_CELLS),
        "matrix_rules": len(names),
        "run13_timing_cells_not_recomputed": 39,
        "family_total_with_run13": len(names) + 39,
        "availability": availability,
        "success_bar": "test win>=70%, win CI lower>50%, expectancy CI lower>0 at 1x and 2x, >=20 test trades, reality p<0.05, DSR>=0.95, validation interval not entirely below zero",
        "rows": rows,
        "any_meets_success_bar": bool(passed),
        "passed": passed,
        "best_mean_rule": names[best],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items()},
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run15.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("ANY", bool(passed), passed)
    print("BEST", names[best], reality.get("p_value"), dsr.get("dsr"), "N", len(names))


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def target_book(state):
    """Run-14 cells reused only inside the family-wise matrix."""
    from rare_setups_run14 import NEW_CELLS as OLD
    from rare_setups_run14 import gap_and_or_trades, target_trades as old_targets, vix_trades
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    ratio = {}
    series = (yahoo["vix"] / yahoo["vix3m"]).shift(1)
    for stamp, value in series.items():
        if np.isfinite(value):
            ratio[stamp.date()] = float(value)
    book = old_targets(state)
    book.update(gap_and_or_trades(state, ratio))
    book.update(vix_trades(state, yahoo))
    return {name: book[name] for name in OLD if name in book}


if __name__ == "__main__":
    main()
