"""Run 18. Fixed before any result is computed.

Two ideas that were not the earlier opening-range continuation or the
single-index trend tests:

1. Nasdaq leads the S&P. A signal uses the prior 30 clock minutes on
   both 5-minute series. Entry is the next USA500 bar. The stop and the
   target are both 0.20%, and a trade is flat after 60 minutes. The
   stop is filled before the target.
2. Fade the opening drive. The signal is the move from the 09:30 open
   to the 10:00 open. Entry is 10:00. Stop and target are 0.20%, and
   the trade is flat at the 11:30 open.
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
from rare_setups_run17 import (
    load_bars,
    net_of_fraction,
    stop_book,
    stopped_path,
    summarize,
    trade,
    vwap_book,
)
from rare_setups_study import COST, build_daily

NEW_CELLS = (
    "nq_lead_long_30m",
    "nq_lead_short_30m",
    "nq_flush_fade_long",
    "nq_flush_fade_short",
    "open_drive_fade_long",
    "open_drive_fade_short",
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


def symbol_paths(prefix: str) -> list[Path]:
    paths = [path for path in sorted(Path("/tmp/rare_data/m5").glob(f"{prefix}*.csv")) if ".part" not in path.name]
    refresh = Path("/tmp/rare_data/refresh") / f"{prefix}-new.csv"
    if refresh.exists():
        paths.append(refresh)
    return paths


def lead_lag(usa: pd.DataFrame, tech: pd.DataFrame) -> dict[str, list[dict]]:
    joined = usa[["open", "close"]].join(tech[["close"]].rename(columns={"close": "tech"}), how="inner")
    now = joined["close"]
    tech_now = joined["tech"]
    prev_clock = joined.index - pd.Timedelta(minutes=30)
    prev = now.reindex(prev_clock)
    prev.index = joined.index
    tech_prev = tech_now.reindex(prev_clock)
    tech_prev.index = joined.index
    es = now / prev - 1
    nq = tech_now / tech_prev - 1
    minute = joined.index.hour * 60 + joined.index.minute
    liquid = (minute >= 9 * 60 + 30) & (minute < 15 * 60 + 30)
    index = joined.index
    opens = joined["open"].to_numpy(float)
    # Path uses the USA500 frame, which has high/low. Map joined stamps back to it.
    locator = {ts: i for i, ts in enumerate(usa.index)}
    state = {
        "open": usa["open"].to_numpy(float),
        "high": usa["high"].to_numpy(float),
        "low": usa["low"].to_numpy(float),
        "close": usa["close"].to_numpy(float),
    }
    book = {name: [] for name in NEW_CELLS[:4]}
    specs = {
        "nq_lead_long_30m": lambda i: nq.iloc[i] >= 0.0025 and -0.0005 <= es.iloc[i] <= 0.0010,
        "nq_lead_short_30m": lambda i: nq.iloc[i] <= -0.0025 and -0.0010 <= es.iloc[i] <= 0.0005,
        "nq_flush_fade_long": lambda i: nq.iloc[i] <= -0.004 and es.iloc[i] <= -0.003,
        "nq_flush_fade_short": lambda i: nq.iloc[i] >= 0.004 and es.iloc[i] >= 0.003,
    }
    sides = {"nq_lead_long_30m": 1, "nq_lead_short_30m": -1, "nq_flush_fade_long": 1, "nq_flush_fade_short": -1}
    usable = np.flatnonzero(liquid & es.notna().to_numpy() & nq.notna().to_numpy())
    for name, rule in specs.items():
        busy_until = -1
        for pos in usable:
            if pos <= busy_until or pos + 1 >= len(index):
                continue
            if not rule(int(pos)):
                continue
            entry_ts = index[pos + 1]
            entry_i = locator.get(entry_ts)
            if entry_i is None:
                continue
            deadline_ts = entry_ts + pd.Timedelta(minutes=55)
            deadline_i = int(usa.index.searchsorted(deadline_ts))
            deadline_i = min(deadline_i, len(usa.index) - 1)
            if deadline_i <= entry_i:
                continue
            entry_px = float(state["open"][entry_i])
            side = sides[name]
            gross = stopped_path(state, entry_i, entry_px, 0.002, 0.002, deadline_i, side)
            book[name].append(trade(entry_ts.date(), gross, entry_px))
            busy_until = pos + 12
    return book


def opening_fade(usa: pd.DataFrame) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS[4:]}
    index = usa.index
    locator = {ts: i for i, ts in enumerate(index)}
    state = {
        "open": usa["open"].to_numpy(float),
        "high": usa["high"].to_numpy(float),
        "low": usa["low"].to_numpy(float),
        "close": usa["close"].to_numpy(float),
    }
    opens_0930 = {}
    opens_1000 = {}
    opens_1130 = {}
    for ts, i in locator.items():
        minute = ts.hour * 60 + ts.minute
        if minute == 9 * 60 + 30:
            opens_0930[ts.date()] = i
        elif minute == 10 * 60:
            opens_1000[ts.date()] = i
        elif minute == 11 * 60 + 30:
            opens_1130[ts.date()] = i
    for day, start_i in opens_0930.items():
        entry_i = opens_1000.get(day)
        flat_i = opens_1130.get(day)
        if entry_i is None or flat_i is None or flat_i <= entry_i:
            continue
        base = float(state["open"][start_i])
        entry_px = float(state["open"][entry_i])
        if base <= 0:
            continue
        move = entry_px / base - 1
        if move <= -0.003:
            gross = stopped_path(state, entry_i, entry_px, 0.002, 0.002, flat_i, 1)
            book["open_drive_fade_long"].append(trade(day, gross, entry_px))
        elif move >= 0.003:
            gross = stopped_path(state, entry_i, entry_px, 0.002, 0.002, flat_i, -1)
            book["open_drive_fade_short"].append(trade(day, gross, entry_px))
    return book


def main() -> None:
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    print("DATA last USA500", usa.index[-1].isoformat(), "USATECH", tech.index[-1].isoformat(), flush=True)
    book = {}
    book.update(lead_lag(usa, tech))
    book.update(opening_fade(usa))
    missing = [name for name in NEW_CELLS if name not in book]
    if missing:
        raise RuntimeError(str(missing))
    print("prior family", flush=True)
    state = prepare_paths(usa)
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
        print(name, "n", test["trades"], "win", test["win_rate"], test.get("win_rate_ci"), "exp", test["expectancy"], test["expectancy_ci"], flush=True)
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
    Path("artifacts/rare_setups/run18.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "BEST", names[best], reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4), "N", len(names))


if __name__ == "__main__":
    main()
