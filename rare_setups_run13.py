"""Run 13. Entry clocks are fixed before the results are read.

The signal is known at the 16:00 ET cash close. Entries are the first live
5-minute print at 16:15, 18:00, 03:00, 08:00, or the baseline 09:30.
The primary exit is the next 16:00 cash close. London, a two-day hold, a
three-day hold, and the first higher cash close are tested only for the
09:30 and 18:00 entries. A flat maintenance quote is not an entry.

The family-wise check uses these cells plus the 51 rules from runs 11 and 12.
Train is 2012-2017, validation 2018-2021, test 2022-01-01 onward.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_END, TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_study import COST, build_daily, metrics, wilson

NY = ZoneInfo("America/New_York")
TRAIN_END = date(2017, 12, 31)
VAL_START = date(2018, 1, 1)
VAL_END = date(2021, 12, 31)
SIGNALS = ("consec5", "rsi2_lt5", "lower_lows_4")
ENTRIES = ("16:15", "18:00", "03:00", "08:00", "09:30")
PRIMARY_EXIT = "next_1600"
EXTRA_EXITS = ("london", "hold2", "hold3", "first_up")
EXTRA_ENTRIES = ("09:30", "18:00")


def load_5m(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, usecols=["timestamp", "open", "high", "low", "close"])
    raw["ts"] = pd.to_datetime(raw["timestamp"], unit="ms", utc=True).dt.tz_convert(NY)
    raw = raw.set_index("ts").sort_index()
    for col in ("open", "high", "low", "close"):
        raw[col] = raw[col].astype(float)
    return raw


def rth_daily(bars: pd.DataFrame) -> pd.DataFrame:
    minute = bars.index.hour * 60 + bars.index.minute
    rth = bars[(minute >= 9 * 60 + 30) & (minute < 16 * 60)]
    grouped = rth.groupby(rth.index.date)
    daily = grouped.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    daily.index = pd.to_datetime(daily.index)
    return daily.dropna()


def signals_on(daily: pd.DataFrame) -> dict[str, pd.Series]:
    close = daily["close"]
    low = daily["low"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 2, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 2, adjust=False).mean()
    rsi2 = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    return {
        "consec5": ((close < close.shift()).rolling(5).sum() == 5),
        "rsi2_lt5": rsi2 < 5,
        "lower_lows_4": ((low < low.shift()).rolling(4).sum() == 4),
    }


def clock_index(index: pd.DatetimeIndex) -> dict[tuple[int, int], pd.DatetimeIndex]:
    stamps = {}
    hours = index.hour
    minutes = index.minute
    for hour, minute in ((16, 15), (18, 0), (3, 0), (8, 0), (9, 30)):
        mask = (hours == hour) & (minutes == minute)
        stamps[(hour, minute)] = index[mask]
    return stamps


def first_clock(stamps: pd.DatetimeIndex, start: pd.Timestamp, limit: pd.Timedelta):
    if len(stamps) == 0:
        return None
    pos = int(stamps.searchsorted(start))
    if pos >= len(stamps):
        return None
    found = stamps[pos]
    if found <= start + limit:
        return found
    return None


def live_bar(bars: pd.DataFrame, stamp: pd.Timestamp) -> bool:
    row = bars.loc[stamp]
    if float(row["high"]) != float(row["low"]):
        return True
    pos = int(bars.index.searchsorted(stamp))
    prev = float(bars["close"].iloc[pos - 1]) if pos else float(row["open"])
    return float(row["open"]) != prev


def entry_stamp(name: str, signal_close: pd.Timestamp, clocks, bars) -> pd.Timestamp | None:
    if name == "16:15":
        found = first_clock(clocks[(16, 15)], signal_close, pd.Timedelta(hours=2))
    elif name == "18:00":
        found = first_clock(clocks[(18, 0)], signal_close, pd.Timedelta(hours=54))
    elif name == "03:00":
        found = first_clock(clocks[(3, 0)], signal_close, pd.Timedelta(hours=70))
    elif name == "08:00":
        found = first_clock(clocks[(8, 0)], signal_close, pd.Timedelta(hours=80))
    else:
        found = first_clock(clocks[(9, 30)], signal_close, pd.Timedelta(hours=80))
    if found is None or not live_bar(bars, found):
        return None
    return found


def build_configs() -> list[tuple[str, str, str]]:
    configs = []
    for signal in SIGNALS:
        for entry in ENTRIES:
            configs.append((signal, entry, PRIMARY_EXIT))
        for entry in EXTRA_ENTRIES:
            for exit_name in EXTRA_EXITS:
                configs.append((signal, entry, exit_name))
    if len(configs) != len(set(configs)):
        raise RuntimeError("duplicate entry/exit cell")
    return configs


def day_ci(trades: list[dict], cost: float) -> list[float] | None:
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
    for _ in range(500):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        pool = [value for i in pick for value in grouped[keys[i]]]
        if pool:
            samples.append(float(np.mean(pool)))
    if len(samples) < 20:
        return None
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def summarize(trades: list[dict], cost: float) -> dict:
    base = metrics(trades, cost)
    base["expectancy_ci"] = day_ci(trades, cost)
    if trades:
        years = TEST_END.year - TEST_START.year + 1
        base["trades_per_year"] = round(base["trades"] / years, 3)
    else:
        base["trades_per_year"] = 0
    return base


def slice_period(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def main() -> None:
    configs = build_configs()
    print(f"PRE-REGISTERED CELLS {len(configs)}", flush=True)
    path = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))[0]
    bars = load_5m(path)
    daily = rth_daily(bars)
    flags = signals_on(daily)
    close_stamp = {}
    minute = bars.index.hour * 60 + bars.index.minute
    close_bars = bars[minute == 15 * 60 + 55]
    for stamp, row in close_bars.iterrows():
        close_stamp[stamp.date()] = (stamp, float(row["close"]))
    session_dates = list(daily.index.date)
    session_pos = {day: i for i, day in enumerate(session_dates)}
    clocks = clock_index(bars.index)
    close_times = pd.DatetimeIndex([close_stamp[day][0] for day in session_dates if day in close_stamp])
    close_prices = {close_stamp[day][0]: close_stamp[day][1] for day in session_dates if day in close_stamp}

    def next_cash_close(after: pd.Timestamp):
        pos = int(close_times.searchsorted(after, side="right"))
        if pos >= len(close_times):
            return None
        stamp = close_times[pos]
        return stamp, close_prices[stamp]

    def cash_close_n_after_signal(signal_day: date, sessions_ahead: int):
        pos = session_pos.get(signal_day)
        if pos is None or pos + sessions_ahead >= len(session_dates):
            return None
        target = session_dates[pos + sessions_ahead]
        if target not in close_stamp:
            return None
        stamp, price = close_stamp[target]
        return stamp, price

    trades_by_cell: dict[str, list[dict]] = {f"{a}__{b}__{c}": [] for a, b, c in configs}
    for signal_name, side in flags.items():
        for signal_day in daily.index[side.fillna(False)]:
            day = signal_day.date()
            if day not in close_stamp:
                continue
            signal_bar, _signal_px = close_stamp[day]
            known_at = signal_bar + pd.Timedelta(minutes=5)
            for entry_name, _exit_unused in {(b, c) for a, b, c in configs if a == signal_name}:
                pass
            entries = {}
            for entry_name in ENTRIES:
                stamp = entry_stamp(entry_name, known_at, clocks, bars)
                if stamp is None or stamp <= known_at:
                    continue
                entries[entry_name] = (stamp, float(bars.at[stamp, "open"]))
            for entry_name, (entry_ts, entry_px) in entries.items():
                exits = {PRIMARY_EXIT: next_cash_close(entry_ts)}
                if entry_name in EXTRA_ENTRIES:
                    london = first_clock(clocks[(3, 0)], entry_ts + pd.Timedelta(minutes=5), pd.Timedelta(hours=70))
                    exits["london"] = None if london is None else (london, float(bars.at[london, "open"]))
                    exits["hold2"] = cash_close_n_after_signal(day, 2)
                    exits["hold3"] = cash_close_n_after_signal(day, 3)
                    first = None
                    for ahead in range(1, 6):
                        candidate = cash_close_n_after_signal(day, ahead)
                        if candidate is None:
                            break
                        if candidate[0] <= entry_ts:
                            continue
                        if candidate[1] > entry_px or ahead == 5:
                            first = candidate
                            if candidate[1] > entry_px:
                                break
                    exits["first_up"] = first
                for exit_name, result in exits.items():
                    key = f"{signal_name}__{entry_name}__{exit_name}"
                    if key not in trades_by_cell or result is None:
                        continue
                    exit_ts, exit_px = result
                    if exit_ts <= entry_ts:
                        continue
                    drift = None
                    morning = first_clock(clocks[(9, 30)], entry_ts + pd.Timedelta(minutes=5), pd.Timedelta(hours=80))
                    if morning is not None and entry_ts < morning <= exit_ts:
                        drift = float(bars.at[morning, "open"]) - entry_px
                    trades_by_cell[key].append({
                        "day": day, "year": day.year, "gross": float(exit_px - entry_px),
                        "side": 1, "drift": drift,
                    })

    rows = []
    test_days = [stamp.date() for stamp in daily.index if TEST_START <= stamp.date() <= TEST_END]
    matrix_names = []
    matrix_cols = []
    calendar = test_days
    # Prior rules, so this run is judged with them rather than instead of them.
    print("rebuilding prior rules", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    m5 = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))[0]
    prior = old_tradebook(yahoo, m5)
    prior.update(new_tradebook(yahoo, load_5m(m5)))
    prior_days = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= TEST_END]
    calendar = sorted(set(test_days) | set(prior_days))
    for name, trades in prior.items():
        matrix_names.append(f"prior::{name}")
        matrix_cols.append(pnl_on_days(trades, calendar, COST))
    for key, trades in trades_by_cell.items():
        test = slice_period(trades, TEST_START, TEST_END)
        val = slice_period(trades, VAL_START, VAL_END)
        train = slice_period(trades, date(2012, 1, 1), TRAIN_END)
        base = summarize(test, COST)
        stress = summarize(test, COST * 2)
        val_m = summarize(val, COST)
        drift_vals = [row["drift"] for row in test if row.get("drift") is not None]
        rows.append({
            "name": key,
            "test": base,
            "test_2x": {"expectancy": stress["expectancy"], "expectancy_ci": stress["expectancy_ci"], "profit_factor": stress["profit_factor"]},
            "validation": {k: val_m[k] for k in ("trades", "win_rate", "expectancy", "expectancy_ci", "profit_factor")},
            "train_trades": len(train),
            "train_expectancy": None if not train else round(float(np.mean([row["gross"] - COST for row in train])), 4),
            "overnight_drift_mean": None if not drift_vals else round(float(np.mean(drift_vals)), 4),
        })
        matrix_names.append(key)
        matrix_cols.append(pnl_on_days(trades, calendar, COST))
        print(key, "test", base["trades"], base["win_rate"], base["expectancy"], base["expectancy_ci"], "drift", rows[-1]["overnight_drift_mean"], flush=True)

    mat = np.column_stack(matrix_cols)
    means = np.nan_to_num(mat.mean(axis=0), nan=-1e9)
    best_i = int(np.argmax(means))
    reality = whites_reality_check(mat, float(mat[:, best_i].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    dsr = deflated_sharpe_of(mat[:, best_i], sr_star)
    survivors = []
    for i, name in enumerate(matrix_names):
        if not name.startswith("prior::"):
            row = next(item for item in rows if item["name"] == name)
            own = whites_reality_check(mat, float(mat[:, i].mean()))
            own_dsr = deflated_sharpe_of(mat[:, i], sr_star)
            ci = row["test"]["expectancy_ci"] or [None, None]
            survives = bool(ci[0] is not None and ci[0] > 0 and own["survives"] and own_dsr["survives"])
            row["family_wise"] = {"reality_p": own["p_value"], "dsr": own_dsr["dsr"], "survives": survives}
            if survives:
                survivors.append(name)
    # Paired difference versus the 09:30 entry, same signal, same next-close exit.
    paired = []
    for signal in SIGNALS:
        base_key = f"{signal}__09:30__next_1600"
        base_map = {row["day"]: row["gross"] for row in trades_by_cell[base_key]}
        for entry in ENTRIES:
            if entry == "09:30":
                continue
            key = f"{signal}__{entry}__next_1600"
            diffs = []
            for row in slice_period(trades_by_cell[key], TEST_START, TEST_END):
                if row["day"] in base_map:
                    diffs.append(row["gross"] - base_map[row["day"]])
            ci = None
            if len(diffs) >= 2:
                rng = np.random.default_rng(16)
                samples = [float(np.mean(rng.choice(diffs, size=len(diffs), replace=True))) for _ in range(500)]
                ci = [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]
            paired.append({
                "signal": signal, "entry": entry, "paired_days": len(diffs),
                "mean_extra_points": None if not diffs else round(float(np.mean(diffs)), 4),
                "extra_ci": ci,
            })
    payload = {
        "preregistered_cells": [f"{a}__{b}__{c}" for a, b, c in configs],
        "cells": len(configs),
        "family_wise_n": len(matrix_names),
        "prior_rules_in_check": sum(1 for name in matrix_names if name.startswith("prior::")),
        "split": {"train": "2012-01-01..2017-12-31", "validation": "2018-01-01..2021-12-31", "test": "2022-01-01..2026-11-11"},
        "cost_round_trip_points": COST,
        "one_minute_note": "Entry clocks are 5-minute boundaries. The 1-minute open at 16:15, 18:00, 03:00, 08:00 and 09:30 is the open of that 5-minute bar, so a separate 1-minute fill was not simulated.",
        "rows": rows,
        "paired_versus_0930": paired,
        "best_family_mean": matrix_names[best_i],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items()},
        "survivors": survivors,
        "live_default": "legacy",
    }
    out = Path("artifacts/rare_setups/run13.json")
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("CELLS", len(configs), "FAMILY", len(matrix_names), "SURVIVORS", survivors)
    print("BEST", matrix_names[best_i], reality.get("p_value"), dsr.get("dsr"))


if __name__ == "__main__":
    main()
