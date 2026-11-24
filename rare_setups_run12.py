"""Run 12. The NEW_RULES list is the pre-registered family.

Nothing is added after the numbers are seen. The family-wise check uses
these rules plus the 22 rules from run 11. The test block is 2022-01-01
through 2026-11-11. Train is 2008-2017 and validation is 2018-2021.
Thresholds are not refit.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_study import (
    CLOSE_TO_CLOSE,
    COST,
    build_daily,
    closeclose_trades,
    daily_rules,
    intraday,
    metrics,
    next_open_trades,
    overnight_trades,
    same_bar_trades,
    walk_forward_rsi,
)

TRAIN_END = date(2017, 12, 31)
VAL_START = date(2018, 1, 1)
VAL_END = date(2021, 12, 31)
TEST_START = date(2022, 1, 1)
TEST_END = date(2026, 11, 11)

# Pre-registered before any result from this run. Names stay stable.
NEW_RULES = (
    "rsi2_lt5_above200",
    "rsi2_lt2_above200",
    "rsi2_gt95_below200_short",
    "rsi2_gt98_below200_short",
    "lower_lows_3",
    "lower_lows_4",
    "higher_highs_3_short",
    "close_bottom10_down",
    "close_top10_up_short",
    "ibs_lt_0.1",
    "ibs_gt_0.9_short",
    "vix_spike_long",
    "vix_inversion_long",
    "gap_reclaim_5m",
    "tom_hold",
    "pre_holiday",
    "fomc_day_long",
    "opex_week",
    "down3_week_long",
    "low52_uptrend",
    "nr7_break_5m",
    "inside_break_5m",
    "double7_long",
    "consec5_above200",
    "consec5_vix_lt20",
    "consec5_vix_gt25",
    "consec5_above200_vix_lt25",
    "consec5up_below200_short",
    "ibs_gt09_below200_short",
)


def _window(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def day_block_ci(trades, cost, days, draws=500, seed=16):
    if len(trades) < 2 or len(days) < 2:
        return None
    grouped = {}
    for row in trades:
        grouped.setdefault(row["day"], []).append(row["gross"] - cost)
    usable = [day for day in days if day in grouped]
    if len(usable) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        pick = rng.choice(len(usable), size=len(usable), replace=True)
        pool = [pnl for i in pick for pnl in grouped[usable[i]]]
        if pool:
            samples.append(float(np.mean(pool)))
    if len(samples) < 20:
        return None
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def pack(trades, start, end, cost=COST):
    chosen = _window(trades, start, end)
    row = metrics(chosen, cost)
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor = date.fromordinal(cursor.toordinal() + 1)
    row["expectancy_ci"] = day_block_ci(chosen, cost, days)
    row["years"] = [item for item in row["years"] if start.year <= item["year"] <= end.year]
    if row["trades"]:
        row["trades_per_year"] = round(row["trades"] / max(1, end.year - start.year + 1), 3)
    else:
        row["trades_per_year"] = 0
    return row


def new_sides(frame: pd.DataFrame) -> dict[str, pd.Series]:
    idx = frame.index
    close = frame["close"]
    high = frame["high"]
    low = frame["low"]
    sma200 = close.rolling(200).mean()
    above = close > sma200
    below = close < sma200
    span = (high - low).replace(0, np.nan)
    ibs = (close - low) / span
    down5 = (close < close.shift()).rolling(5).sum() == 5
    up5 = (close > close.shift()).rolling(5).sum() == 5
    vix_ma10 = frame["vix"].rolling(10).mean()
    from rare_setups_study import FOMC
    fomc = {pd.Timestamp(day) for day in FOMC}
    sides = {
        "rsi2_lt5_above200": ((frame["rsi2"] < 5) & above).astype(int),
        "rsi2_lt2_above200": ((frame["rsi2"] < 2) & above).astype(int),
        "rsi2_gt95_below200_short": ((frame["rsi2"] > 95) & below).astype(int) * -1,
        "rsi2_gt98_below200_short": ((frame["rsi2"] > 98) & below).astype(int) * -1,
        "lower_lows_3": ((low < low.shift(1)).rolling(3).sum() == 3).astype(int),
        "lower_lows_4": ((low < low.shift(1)).rolling(4).sum() == 4).astype(int),
        "higher_highs_3_short": ((high > high.shift(1)).rolling(3).sum() == 3).astype(int) * -1,
        "close_bottom10_down": ((ibs < 0.1) & (close < close.shift())).astype(int),
        "close_top10_up_short": ((ibs > 0.9) & (close > close.shift())).astype(int) * -1,
        "ibs_lt_0.1": (ibs < 0.1).astype(int),
        "ibs_gt_0.9_short": (ibs > 0.9).astype(int) * -1,
        "vix_spike_long": (frame["vix"] >= 1.2 * vix_ma10).astype(int),
        "vix_inversion_long": (frame["vix"] > frame["vix3m"]).astype(int),
        "consec5_above200": (down5 & above).astype(int),
        "consec5_vix_lt20": (down5 & (frame["vix"] < 20)).astype(int),
        "consec5_vix_gt25": (down5 & (frame["vix"] > 25)).astype(int),
        "consec5_above200_vix_lt25": (down5 & above & (frame["vix"] < 25)).astype(int),
        "consec5up_below200_short": (up5 & below).astype(int) * -1,
        "ibs_gt09_below200_short": ((ibs > 0.9) & below).astype(int) * -1,
        "low52_uptrend": ((low <= low.rolling(252).min()) & (sma200 > sma200.shift(20))).astype(int),
        "fomc_day_long": pd.Series([1 if stamp.normalize() in fomc else 0 for stamp in idx], index=idx),
    }
    return {name: series.fillna(0).astype(int) for name, series in sides.items()}


def hold_trades(frame: pd.DataFrame, entry_mask: pd.Series, hold: int, side: int = 1) -> list[dict]:
    rows = []
    idx = frame.index
    flags = entry_mask.fillna(False).to_numpy()
    last_exit = -1
    for i, flag in enumerate(flags):
        if not flag or i + hold >= len(idx) or i <= last_exit:
            continue
        gross = side * (float(frame["close"].iloc[i + hold]) - float(frame["open"].iloc[i + 1]))
        day = idx[i + hold].date()
        rows.append({"day": day, "year": day.year, "gross": float(gross), "side": side})
        last_exit = i + hold
    return rows


def tom_trades(frame: pd.DataFrame) -> list[dict]:
    idx = frame.index
    rows = []
    for i, stamp in enumerate(idx[:-3]):
        nxt = idx[i + 1]
        if nxt.month == stamp.month:
            continue
        gross = float(frame["close"].iloc[i + 3] - frame["close"].iloc[i])
        day = idx[i + 3].date()
        rows.append({"day": day, "year": day.year, "gross": gross, "side": 1})
    return rows


def holiday_trades(frame: pd.DataFrame) -> list[dict]:
    idx = frame.index
    rows = []
    for i, stamp in enumerate(idx[:-1]):
        if (idx[i + 1] - stamp).days < 4:
            continue
        gross = float(frame["open"].iloc[i + 1] - frame["close"].iloc[i])
        day = idx[i + 1].date()
        rows.append({"day": day, "year": day.year, "gross": gross, "side": 1})
    return rows


def opex_week_trades(frame: pd.DataFrame) -> list[dict]:
    from rare_setups_study import third_fridays
    fridays = third_fridays(frame.index)
    idx = frame.index
    rows = []
    for i, stamp in enumerate(idx):
        if stamp.date() not in fridays or i < 4:
            continue
        monday = idx[i - 4]
        if monday.date() > stamp.date() or (stamp - monday).days > 6:
            continue
        gross = float(frame["close"].iloc[i] - frame["open"].iloc[i - 4])
        rows.append({"day": stamp.date(), "year": stamp.year, "gross": gross, "side": 1})
    return rows


def down_week_trades(frame: pd.DataFrame) -> list[dict]:
    ret5 = frame["close"].pct_change(5)
    mask = (ret5 <= -0.03).fillna(False)
    return hold_trades(frame, mask, 5, 1)


def double7_trades(frame: pd.DataFrame) -> list[dict]:
    close = frame["close"]
    low7 = close.rolling(7).min()
    rows = []
    idx = frame.index
    i = 7
    while i < len(frame) - 1:
        if close.iloc[i] <= low7.iloc[i]:
            entry = i + 1
            exit_i = None
            for j in range(entry, min(len(frame), entry + 7)):
                window = close.iloc[j - 6: j + 1]
                if close.iloc[j] >= window.max():
                    exit_i = j
                    break
            if exit_i is None:
                exit_i = min(len(frame) - 1, entry + 6)
            gross = float(close.iloc[exit_i] - frame["open"].iloc[entry])
            day = idx[exit_i].date()
            rows.append({"day": day, "year": day.year, "gross": gross, "side": 1})
            i = exit_i + 1
        else:
            i += 1
    return rows


def _five_minute(path: Path) -> pd.DataFrame:
    raw = pd.read_csv(path, usecols=["timestamp", "open", "high", "low", "close"])
    raw["ts"] = pd.to_datetime(raw["timestamp"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    return raw.set_index("ts").sort_index()


def path_break_trades(raw: pd.DataFrame, setup_days: dict[date, tuple[float, float]], name: str) -> list[dict]:
    """Next session, enter after a 5-minute close through the prior high or low."""
    raw = raw.copy()
    raw["day"] = raw.index.date
    raw["minute"] = raw.index.hour * 60 + raw.index.minute
    trades = []
    for day, chunk in raw.groupby("day"):
        if day not in setup_days:
            continue
        level_high, level_low = setup_days[day]
        rth = chunk[(chunk["minute"] >= 9 * 60 + 30) & (chunk["minute"] < 16 * 60)]
        if len(rth) < 6 or not np.isfinite(level_high) or not np.isfinite(level_low) or level_high <= level_low:
            continue
        values = rth.reset_index()
        entered = None
        for i in range(len(values) - 1):
            px = float(values.loc[i, "close"])
            if px > level_high:
                entered = (1, i)
                break
            if px < level_low:
                entered = (-1, i)
                break
        if entered is None:
            continue
        sgn, i = entered
        if i + 1 >= len(values):
            continue
        quote = float(values.loc[i + 1, "open"])
        width = level_high - level_low
        stop = quote - sgn * width
        target = quote + sgn * width
        exit_price = None
        for j in range(i + 1, len(values)):
            if sgn > 0 and values.loc[j, "low"] <= stop:
                exit_price = stop
                break
            if sgn < 0 and values.loc[j, "high"] >= stop:
                exit_price = stop
                break
            if sgn > 0 and values.loc[j, "high"] >= target:
                exit_price = target
                break
            if sgn < 0 and values.loc[j, "low"] <= target:
                exit_price = target
                break
            exit_price = float(values.loc[j, "close"])
        gross = sgn * (exit_price - quote)
        trades.append({"day": day, "year": day.year, "gross": float(gross), "side": sgn, "rule": name})
    return trades


def gap_reclaim_trades(raw: pd.DataFrame, daily: pd.DataFrame | None = None) -> list[dict]:
    """Gap is the 09:30 open versus the prior regular-session close, both on USA500."""
    work = raw.copy()
    work["day"] = work.index.date
    work["minute"] = work.index.hour * 60 + work.index.minute
    rth = work[(work["minute"] >= 9 * 60 + 30) & (work["minute"] < 16 * 60)]
    sessions = []
    for day, chunk in rth.groupby("day"):
        if len(chunk) < 6:
            continue
        sessions.append((day, float(chunk["open"].iloc[0]), float(chunk["close"].iloc[-1]), chunk))
    trades = []
    for i in range(1, len(sessions)):
        day, opener, _close, chunk = sessions[i]
        prev_close = sessions[i - 1][2]
        if prev_close <= 0 or opener / prev_close - 1 > -0.01:
            continue
        values = chunk.reset_index()
        hit = None
        for j in range(len(values) - 1):
            if float(values.loc[j, "close"]) > prev_close:
                hit = j
                break
        if hit is None:
            continue
        quote = float(values.loc[hit + 1, "open"])
        exit_price = float(values.loc[len(values) - 1, "close"])
        trades.append({"day": day, "year": day.year, "gross": float(exit_price - quote), "side": 1})
    return trades


def nr_inside_maps(daily: pd.DataFrame) -> tuple[dict, dict]:
    rng = daily["high"] - daily["low"]
    nr7 = rng == rng.rolling(7).min()
    inside = (daily["high"] < daily["high"].shift()) & (daily["low"] > daily["low"].shift())
    nr_map = {}
    inside_map = {}
    idx = daily.index
    for i, stamp in enumerate(idx[:-1]):
        nxt = idx[i + 1].date()
        if bool(nr7.iloc[i]):
            nr_map[nxt] = (float(daily["high"].iloc[i]), float(daily["low"].iloc[i]))
        if bool(inside.iloc[i]):
            inside_map[nxt] = (float(daily["high"].iloc[i]), float(daily["low"].iloc[i]))
    return nr_map, inside_map


def old_tradebook(frame: pd.DataFrame, m5_path: Path | None) -> dict[str, list[dict]]:
    rules = daily_rules(frame)
    book = {}
    for name, side in rules.items():
        if name in {"overnight_all", "overnight_contango", "overnight_tom"}:
            book[name] = overnight_trades(frame, side)
        elif name in CLOSE_TO_CLOSE:
            book[name] = closeclose_trades(frame, side)
        elif name in {"gap_fade", "gap_go", "nfp_gap_fade"}:
            book[name] = same_bar_trades(frame, side)
        else:
            book[name] = next_open_trades(frame, side)
    book["rsi2_walkforward_5_or_10"] = walk_forward_rsi(frame)
    if m5_path and m5_path.exists():
        book.update(intraday(m5_path))
    return book


def new_tradebook(frame: pd.DataFrame, raw: pd.DataFrame | None) -> dict[str, list[dict]]:
    sides = new_sides(frame)
    book = {name: next_open_trades(frame, side) for name, side in sides.items() if name != "fomc_day_long"}
    from rare_setups_study import same_bar_trades as same
    book["fomc_day_long"] = same(frame, sides["fomc_day_long"])
    book["tom_hold"] = tom_trades(frame)
    book["pre_holiday"] = holiday_trades(frame)
    book["opex_week"] = opex_week_trades(frame)
    book["down3_week_long"] = down_week_trades(frame)
    book["double7_long"] = double7_trades(frame)
    if raw is not None:
        nr_map, inside_map = nr_inside_maps(frame)
        book["nr7_break_5m"] = path_break_trades(raw, nr_map, "nr7")
        book["inside_break_5m"] = path_break_trades(raw, inside_map, "inside")
        book["gap_reclaim_5m"] = gap_reclaim_trades(raw, frame)
    missing = [name for name in NEW_RULES if name not in book]
    if missing:
        raise RuntimeError(f"missing pre-registered rules: {missing}")
    return book


def pnl_on_days(trades, days, cost):
    grouped = {day: 0.0 for day in days}
    for row in trades:
        if row["day"] in grouped:
            grouped[row["day"]] += row["gross"] - cost
    return np.array([grouped[day] for day in days], dtype=float)


def ensemble(members: list[tuple[str, list[dict]]], test_days: list[date]) -> list[dict]:
    """One trade per day. Same direction keeps the first registered name. Opposites are dropped."""
    by_day: dict[date, list[dict]] = {}
    for name, trades in members:
        for row in trades:
            if row["day"] not in test_days and not (TEST_START <= row["day"] <= TEST_END):
                continue
            if not (TEST_START <= row["day"] <= TEST_END):
                continue
            item = dict(row)
            item["rule"] = name
            by_day.setdefault(row["day"], []).append(item)
    kept = []
    for day in sorted(by_day):
        sides = {row["side"] for row in by_day[day]}
        if len(sides) != 1:
            continue
        kept.append(by_day[day][0])
    return kept


def main() -> None:
    print("PRE-REGISTERED", len(NEW_RULES))
    for name in NEW_RULES:
        print(" -", name, flush=True)
    frame = build_daily(Path("/tmp/rare_data/daily"))[0]
    m5_files = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))
    m5_path = m5_files[0] if m5_files else None
    print("loading 5m" if m5_path else "no 5m", flush=True)
    raw = _five_minute(m5_path) if m5_path else None
    book = old_tradebook(frame, m5_path)
    book.update(new_tradebook(frame, raw))
    test_days = [stamp.date() for stamp in frame.index if TEST_START <= stamp.date() <= TEST_END]
    rows = []
    matrix_names = []
    matrix = []
    val_candidates = []
    for name, trades in book.items():
        test = pack(trades, TEST_START, TEST_END, COST)
        test2 = pack(trades, TEST_START, TEST_END, COST * 2)
        val = pack(trades, VAL_START, VAL_END, COST)
        train = pack(trades, date(2008, 1, 1), TRAIN_END, COST)
        rows.append({
            "name": name,
            "family": "run12" if name in NEW_RULES else "run11",
            "test": test, "test_2x": {"expectancy": test2["expectancy"], "expectancy_ci": test2["expectancy_ci"], "profit_factor": test2["profit_factor"]},
            "validation": {k: val[k] for k in ("trades", "win_rate", "expectancy", "expectancy_ci", "profit_factor")},
            "train": {k: train[k] for k in ("trades", "expectancy", "profit_factor")},
        })
        matrix_names.append(name)
        matrix.append(pnl_on_days(trades, test_days, COST))
        ci = val["expectancy_ci"] or [None, None]
        if val["trades"] >= 8 and ci[0] is not None and ci[0] > 0 and (val["profit_factor"] or 0) > 1.3:
            val_candidates.append(name)
        print(f"{name:32} test n={test['trades']:4} win={test['win_rate']} exp={test['expectancy']} ci={test['expectancy_ci']}", flush=True)
    mat = np.column_stack(matrix)
    best_i = int(np.nanargmax(mat.mean(axis=0)))
    reality = whites_reality_check(mat, float(mat[:, best_i].mean()))
    sr_star = deflated_sharpe(mat, mat.shape[1])["sr_star"]
    dsr = deflated_sharpe_of(mat[:, best_i], sr_star)
    survivors = []
    for i, name in enumerate(matrix_names):
        own = whites_reality_check(mat, float(mat[:, i].mean()))
        own_dsr = deflated_sharpe_of(mat[:, i], sr_star)
        test = rows[i]["test"]
        ci = test["expectancy_ci"] or [None, None]
        survives = bool(ci[0] is not None and ci[0] > 0 and own["survives"] and own_dsr["survives"])
        rows[i]["family_wise"] = {"reality_p": own["p_value"], "dsr": own_dsr["dsr"], "survives": survives}
        if survives:
            survivors.append(name)
    locked = [(name, book[name]) for name in val_candidates]
    ens = ensemble(locked, test_days)
    ens_stats = pack(ens, TEST_START, TEST_END, COST)
    ens_2x = pack(ens, TEST_START, TEST_END, COST * 2)
    payload = {
        "preregistered_new_rules": list(NEW_RULES),
        "run11_rules_included": sorted(name for name in book if name not in NEW_RULES),
        "configs_this_run_new": len(NEW_RULES),
        "configs_family_wise": len(matrix_names),
        "split": {"train": "2008-01-01..2017-12-31", "validation": "2018-01-01..2021-12-31", "test": "2022-01-01..2026-11-11"},
        "cost_round_trip_points": COST,
        "rows": rows,
        "best_test_mean_rule": matrix_names[best_i],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items()},
        "family_wise_survivors": survivors,
        "validation_locked_members": val_candidates,
        "ensemble_test": ens_stats,
        "ensemble_test_2x": {"expectancy": ens_2x["expectancy"], "expectancy_ci": ens_2x["expectancy_ci"], "profit_factor": ens_2x["profit_factor"]},
        "live_default": "legacy",
    }
    out = Path("artifacts/rare_setups")
    out.mkdir(parents=True, exist_ok=True)
    (out / "run12.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("SURVIVORS", survivors)
    print("VAL MEMBERS", val_candidates)
    print("ENSEMBLE", ens_stats["trades"], ens_stats["expectancy"], ens_stats["expectancy_ci"])
    print("BEST", matrix_names[best_i], reality["p_value"], dsr["dsr"])


if __name__ == "__main__":
    main()
