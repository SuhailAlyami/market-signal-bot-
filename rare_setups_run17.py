"""Run 17. Fixed before any result is computed.

The new family is a price stop on the three carry-over longs, plus a
15:00 stretch back toward the cash-session average. Runs 14 and 15 took
a profit target and otherwise waited for the session close, so a loser
could be very large. These cells exit at a stop the same size as the
target, and the stop is filled before the target when one bar hits both.

The replication is one rule, chosen here: RSI(2)<5, enter 18:00, stop
0.50%, target 0.50%, flat at the close three sessions later. It is
repeated on USATECH. A pass still requires the S&P test to clear the
full family check. The Nasdaq result does not replace that check.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp, live_bar
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import TRAIN_END, TRAIN_START, calendar_book, trend_book, window_book
from rare_setups_study import COST, build_daily, metrics

NY_OFFSET = "America/New_York"
PAIRS = (
    ("rsi2_lt5", 0.004, 0.004),
    ("rsi2_lt5", 0.005, 0.005),
    ("rsi2_lt5", 0.0075, 0.0075),
    ("consec5", 0.005, 0.005),
    ("lower_lows_4", 0.005, 0.005),
)
STOP_CELLS = tuple(f"{signal}__18:00__s{stop}_t{target}_d3" for signal, stop, target in PAIRS)
VWAP_CELLS = ("vwap_stretch_long_1500", "vwap_stretch_short_1500")
NEW_CELLS = STOP_CELLS + VWAP_CELLS
CONFIRM_NAME = "confirm_usatech_rsi2_s0.005_t0.005_d3"


def load_bars(paths: list[Path]) -> pd.DataFrame:
    frames = [pd.read_csv(path, usecols=["timestamp", "open", "high", "low", "close"]) for path in paths]
    raw = pd.concat(frames, ignore_index=True).drop_duplicates("timestamp", keep="last")
    raw["ts"] = pd.to_datetime(raw["timestamp"], unit="ms", utc=True).dt.tz_convert(NY_OFFSET)
    raw = raw.set_index("ts").sort_index()
    for col in ("open", "high", "low", "close"):
        raw[col] = raw[col].astype(float)
    return raw


def trade(day: date, gross: float, entry: float) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": 1, "entry": float(entry)}


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def stopped_path(state, entry_i: int, entry_px: float, target: float, stop: float, deadline: int, side: int = 1) -> float:
    """Stop is tested before the target. A gap through either level fills at the open."""
    if side == 1:
        stop_px = entry_px * (1 - stop)
        target_px = entry_px * (1 + target)
    else:
        stop_px = entry_px * (1 + stop)
        target_px = entry_px * (1 - target)
    opens = state["open"]
    highs = state["high"]
    lows = state["low"]
    for j in range(entry_i, deadline + 1):
        if side == 1:
            if opens[j] <= stop_px:
                return float(opens[j] - entry_px)
            if lows[j] <= stop_px:
                return float(stop_px - entry_px)
            if opens[j] >= target_px:
                return float(opens[j] - entry_px)
            if highs[j] >= target_px:
                return float(target_px - entry_px)
        else:
            if opens[j] >= stop_px:
                return float(entry_px - opens[j])
            if highs[j] >= stop_px:
                return float(entry_px - stop_px)
            if opens[j] <= target_px:
                return float(entry_px - opens[j])
            if lows[j] <= target_px:
                return float(entry_px - target_px)
    last = float(state["close"][deadline])
    return float(side * (last - entry_px))


def stop_book(state) -> dict[str, list[dict]]:
    book = {name: [] for name in STOP_CELLS}
    index = state["index"]
    for signal, stop, target in PAIRS:
        name = f"{signal}__18:00__s{stop}_t{target}_d3"
        side = state["flags"][signal]
        for stamp in side.index[side.fillna(False)]:
            day = stamp.date()
            known = state["close_i"].get(day)
            pos = state["pos"].get(day)
            if known is None or pos is None or pos + 3 >= len(state["session_dates"]):
                continue
            far = state["close_i"].get(state["session_dates"][pos + 3])
            entry_ts = entry_stamp("18:00", index[known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
            if entry_ts is None or far is None:
                continue
            entry_i = int(index.searchsorted(entry_ts))
            if far <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            gross = stopped_path(state, entry_i, entry_px, target, stop, far, 1)
            book[name].append(trade(day, gross, entry_px))
    return book


def vwap_book(state) -> dict[str, list[dict]]:
    book = {name: [] for name in VWAP_CELLS}
    index = state["index"]
    buckets: dict[date, list[int]] = {}
    for i, ts in enumerate(index):
        minute = ts.hour * 60 + ts.minute
        if 9 * 60 + 30 <= minute < 16 * 60:
            buckets.setdefault(ts.date(), []).append(i)
    high = state["high"]
    low = state["low"]
    close = state["close"]
    bars = state["bars"]
    for day, rows in buckets.items():
        by_clock = {index[i].hour * 60 + index[i].minute: i for i in rows}
        entry_i = by_clock.get(15 * 60)
        anchor_i = by_clock.get(14 * 60 + 55)
        flat_i = by_clock.get(15 * 60 + 55)
        if entry_i is None or anchor_i is None or flat_i is None or flat_i <= entry_i:
            continue
        if not live_bar(bars, index[entry_i]):
            continue
        prior = [i for i in rows if i <= anchor_i]
        if len(prior) < 30:
            continue
        average = float(np.mean((high[prior] + low[prior] + close[prior]) / 3))
        if not np.isfinite(average) or average <= 0:
            continue
        entry_px = float(state["open"][entry_i])
        stretch = close[anchor_i] / average - 1
        # The open must still be on the stretched side of the average.
        if stretch <= -0.0025 and entry_px < average:
            gross = stopped_path(state, entry_i, entry_px, average / entry_px - 1, 0.0025, flat_i, 1)
            book["vwap_stretch_long_1500"].append(trade(day, gross, entry_px))
        elif stretch >= 0.0025 and entry_px > average:
            gross = stopped_path(state, entry_i, entry_px, 1 - average / entry_px, 0.0025, flat_i, -1)
            book["vwap_stretch_short_1500"].append(trade(day, gross, entry_px))
    return book


def summarize(trades, cost: float) -> dict:
    return metrics(trades, cost)


def net_of_fraction(trades, fraction: float) -> list[dict]:
    out = []
    for row in trades:
        item = dict(row)
        item["gross"] = row["gross"] - fraction * row["entry"]
        out.append(item)
    return out


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
    return {k: row.get(k) for k in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss", "years_positive")}


def main() -> None:
    if len(NEW_CELLS) != len(set(NEW_CELLS)):
        raise RuntimeError("duplicate cell")
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    print("CONFIRM", CONFIRM_NAME, "USATECH same stop and target", flush=True)
    usa_paths = [path for path in sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv")) if ".part" not in path.name]
    tech_paths = [path for path in sorted(Path("/tmp/rare_data/m5").glob("usatech*.csv")) if ".part" not in path.name]
    refresh = Path("/tmp/rare_data/refresh")
    if (refresh / "usa500-new.csv").exists():
        usa_paths.append(refresh / "usa500-new.csv")
    if (refresh / "usatech-new.csv").exists():
        tech_paths.append(refresh / "usatech-new.csv")
    bars = load_bars(usa_paths)
    print("DATA last USA500 bar", bars.index[-1].isoformat(), "rows", len(bars), flush=True)
    state = prepare_paths(bars)
    book = {}
    book.update(stop_book(state))
    book.update(vwap_book(state))
    missing = [name for name in NEW_CELLS if name not in book]
    if missing:
        raise RuntimeError(str(missing))
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    test_end = max(stamp.date() for stamp in yahoo.index if stamp.date() <= date(2026, 11, 12))
    prior = old_tradebook(yahoo, usa_paths[0])
    prior.update(new_tradebook(yahoo, bars))
    prior.update(target_book(state))
    prior.update(window_book(state))
    prior.update(calendar_book(state))
    prior.update(trend_book(bars))
    prior.update(build_book(state, cross_asset(Path("/tmp/rare_data/daily")), state["close"]))
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
        print(name, "n", test["trades"], "win", test["win_rate"], test.get("win_rate_ci"), "exp", test["expectancy"], test["expectancy_ci"], "pf", test["profit_factor"], flush=True)
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
    tech = load_bars(tech_paths)
    tech_state = prepare_paths(tech)
    confirm_rows = stop_book(tech_state)["rsi2_lt5__18:00__s0.005_t0.005_d3"]
    # Breadth is not part of this replication. The stop itself is the new idea.
    sample = keep(confirm_rows, TEST_START, test_end)
    confirm_test = summarize(net_of_fraction(sample, 0.0002), 0.0)
    confirm_stress = summarize(net_of_fraction(sample, 0.0004), 0.0)
    payload = {
        "preregistered": list(NEW_CELLS),
        "new_cells": len(NEW_CELLS),
        "data_last_bar": bars.index[-1].isoformat(),
        "test_end": str(test_end),
        "cash_session_note": "The latest completed Yahoo cash close is the test end. Futures include the overnight prints available at the download.",
        "matrix_rules": len(names),
        "run13_timing_cells_not_recomputed": 39,
        "family_total_with_run13": len(names) + 39,
        "rows": rows,
        "any_meets_success_bar": bool(passed),
        "passed": passed,
        "best_mean_rule": names[best],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items() if k != "trial_sharpes"},
        "confirmatory": {
            "name": CONFIRM_NAME,
            "definition": "USATECH RSI(2)<5, 18:00 entry, 0.50% stop, 0.50% target, three-session time stop. Cost 0.02% of entry, 0.04% at 2x. No RSP/IWM filter.",
            "test": slim(confirm_test),
            "test_2x": slim(confirm_stress),
        },
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run17.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed)
    print("BEST", names[best], reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4), "N", len(names))
    print("CONFIRM", confirm_test.get("trades"), confirm_test.get("win_rate"), confirm_test.get("expectancy"), confirm_test.get("expectancy_ci"))


if __name__ == "__main__":
    main()
