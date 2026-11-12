"""Run 20. The rule list is fixed before any trade result is computed.

Price-only families are not repeated. These five rules use data that was
not in the earlier signal set.

1. front_backwardation_long. At the cash close, VIX9D is above VIX, VIX is
   above VIX3M, and VIX has just made a 20-session high. Short-dated fear
   is richer than both 30-day and 3-month fear, and the spike is new.
   Enter 18:00 ET. Exit at the 15:55 close three cash sessions later.
2. vvix_blowoff_long. VVIX rises at least 10% on the day and VIX rises at
   least 5%. The options market is paying up for volatility convexity.
   Enter 18:00. Exit two cash sessions later.
3. skew_unwind_long. SKEW was at least 145 sometime in the prior five
   sessions and today's SKEW is at least 8 points under that high, while
   VIX remains below VIX3M. Crash-hedge demand is being taken off without
   a fresh term-structure inversion. Enter 18:00. Exit three sessions later.
4. cot_crowded_short_long. CFTC financial-futures report, S&P 500 Consolidated.
   Asset-manager net (long minus short) is at or below the 10th percentile
   of the prior 52 reports, and leveraged-fund net is at or below the 20th
   percentile of the prior 52. The report date is Tuesday and the release
   is the Friday three days later. Enter 18:00 on the first cash session
   on or after that Friday. Exit five cash sessions later.
5. curve_uninversion_long. The Treasury 10-year minus 2-year yield was
   negative on each of the prior 20 published days and is no longer
   negative. Enter the next cash session at 09:30, not the same afternoon,
   and exit ten cash sessions after that entry.

One position per rule. A new signal is ignored until the prior exit.
Exits are time exits. No profit target is used.

The replication is the same five rules on USATECH, same clocks. A rule
passes only if the S&P test and the USATECH replication both clear the
new bar, and the S&P column also survives the reality check across every
rule tested so far.

Sources that could not be used, and why, are written into the output
before the trade statistics are interpreted. Put/call files from Cboe
stop on 2019-10-04. FRED did not respond. AAII returned 403.
"""
from __future__ import annotations

import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp, live_bar
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import build_book, cross_asset, target_book
from rare_setups_run16 import TRAIN_END, TRAIN_START, calendar_book, trend_book, window_book
from rare_setups_run17 import load_bars, net_of_fraction, stop_book, summarize, vwap_book
from rare_setups_run18 import lead_lag, opening_fade, symbol_paths
from rare_setups_run19 import weekly_book
from rare_setups_study import COST, build_daily

NEW_CELLS = (
    "front_backwardation_long",
    "vvix_blowoff_long",
    "skew_unwind_long",
    "cot_crowded_short_long",
    "curve_uninversion_long",
)
HOLDS = {
    "front_backwardation_long": 3,
    "vvix_blowoff_long": 2,
    "skew_unwind_long": 3,
    "cot_crowded_short_long": 5,
    "curve_uninversion_long": 10,
}
EXTERNAL = Path("/tmp/rare_data/external")


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def trade(day: date, gross: float, entry: float) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": 1, "entry": float(entry)}


def slim(row: dict) -> dict:
    return {k: row.get(k) for k in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss", "years_positive", "years")}


def cboe_close(name: str) -> pd.Series:
    frame = pd.read_csv(EXTERNAL / "cboe" / name)
    frame["DATE"] = pd.to_datetime(frame["DATE"], format="%m/%d/%Y")
    value = "CLOSE" if "CLOSE" in frame.columns else frame.columns[-1]
    series = frame.set_index("DATE")[value].astype(float).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    return series


def load_curve() -> pd.Series:
    frames = []
    for path in sorted((EXTERNAL / "treasury").glob("*.csv")):
        frame = pd.read_csv(path)
        if "10 Yr" not in frame.columns or "2 Yr" not in frame.columns:
            continue
        frame["Date"] = pd.to_datetime(frame["Date"], format="%m/%d/%Y")
        frames.append(frame[["Date", "10 Yr", "2 Yr"]])
    all_rows = pd.concat(frames, ignore_index=True).dropna()
    all_rows = all_rows.drop_duplicates("Date", keep="last").sort_values("Date")
    spread = all_rows.set_index("Date")["10 Yr"] - all_rows.set_index("Date")["2 Yr"]
    return spread.astype(float)


def load_cot() -> pd.DataFrame:
    """CFTC Traders in Financial Futures. The continuous line is S&P 500
    Consolidated. The standalone E-mini name is missing from the early files."""
    rows = []
    for path in sorted((EXTERNAL / "cftc").glob("fut_fin_*.zip")):
        if path.stat().st_size < 1000:
            continue
        with zipfile.ZipFile(path) as archive:
            raw = archive.read(archive.namelist()[0]).decode("latin1", errors="replace")
        frame = pd.read_csv(pd.io.common.StringIO(raw))
        frame.columns = [col.strip().strip('"') for col in frame.columns]
        name = frame["Market_and_Exchange_Names"].astype(str).str.strip().str.strip('"')
        picked = frame[name.eq("S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE")].copy()
        if picked.empty:
            continue
        date_col = "Report_Date_as_YYYY-MM-DD" if "Report_Date_as_YYYY-MM-DD" in picked.columns else "Report_Date_as_MM_DD_YYYY"
        picked["asof"] = pd.to_datetime(picked[date_col])
        picked["am_net"] = picked["Asset_Mgr_Positions_Long_All"] - picked["Asset_Mgr_Positions_Short_All"]
        picked["lev_net"] = picked["Lev_Money_Positions_Long_All"] - picked["Lev_Money_Positions_Short_All"]
        rows.append(picked[["asof", "am_net", "lev_net"]])
    book = pd.concat(rows, ignore_index=True).dropna()
    return book.drop_duplicates("asof", keep="last").sort_values("asof")


def trailing_flag(values: np.ndarray, window: int, quantile: float) -> np.ndarray:
    flag = np.zeros(len(values), dtype=bool)
    for i in range(window, len(values)):
        history = values[i - window:i]
        flag[i] = values[i] <= np.quantile(history, quantile)
    return flag


def features() -> dict[str, list[date]]:
    vix = cboe_close("VIX_History.csv")
    vix9d = cboe_close("VIX9D_History.csv")
    vix3m = cboe_close("VIX3M_History.csv")
    skew = cboe_close("SKEW_History.csv")
    vvix = cboe_close("VVIX_History.csv")
    aligned = pd.DataFrame({"vix": vix, "vix9d": vix9d, "vix3m": vix3m, "skew": skew, "vvix": vvix}).dropna()
    prior_high = aligned["vix"].shift(1).rolling(20).max()
    front = aligned.index[(aligned["vix9d"] > aligned["vix"]) & (aligned["vix"] > aligned["vix3m"]) & (aligned["vix"] > prior_high)]
    vvix_jump = aligned["vvix"].pct_change() >= 0.10
    vix_jump = aligned["vix"].pct_change() >= 0.05
    blowoff = aligned.index[vvix_jump & vix_jump]
    skew_high = aligned["skew"].rolling(5).max().shift(1)
    unwind = aligned.index[(skew_high >= 145) & (aligned["skew"] <= skew_high - 8) & (aligned["vix"] < aligned["vix3m"])]
    cot = load_cot()
    am_flag = trailing_flag(cot["am_net"].to_numpy(float), 52, 0.10)
    lev_flag = trailing_flag(cot["lev_net"].to_numpy(float), 52, 0.20)
    release_days = []
    for asof, am_ok, lev_ok in zip(cot["asof"], am_flag, lev_flag):
        if am_ok and lev_ok:
            release_days.append((pd.Timestamp(asof) + pd.Timedelta(days=3)).date())
    curve = load_curve()
    prior_negative = (curve < 0).rolling(20).sum().shift(1) == 20
    curve_days = [stamp.date() for stamp in curve.index[prior_negative & (curve >= 0)]]
    return {
        "front_backwardation_long": [stamp.date() for stamp in front],
        "vvix_blowoff_long": [stamp.date() for stamp in blowoff],
        "skew_unwind_long": [stamp.date() for stamp in unwind],
        "cot_crowded_short_long": release_days,
        "curve_uninversion_long": curve_days,
        "_ranges": {
            "vix": [str(vix.index.min().date()), str(vix.index.max().date())],
            "vix9d": [str(vix9d.index.min().date()), str(vix9d.index.max().date())],
            "vix3m": [str(vix3m.index.min().date()), str(vix3m.index.max().date())],
            "vvix": [str(vvix.index.min().date()), str(vvix.index.max().date())],
            "skew": [str(skew.index.min().date()), str(skew.index.max().date())],
            "cot": [str(cot["asof"].min().date()), str(cot["asof"].max().date()), int(len(cot))],
            "curve": [str(curve.index.min().date()), str(curve.index.max().date())],
        },
    }


def open_map(state) -> dict[date, int]:
    found = {}
    index = state["index"]
    for ts in state["clocks"][(9, 30)]:
        if live_bar(state["bars"], ts):
            found[ts.date()] = int(index.searchsorted(ts))
    return found


def first_session_on_or_after(dates: list[date], day: date) -> date | None:
    for item in dates:
        if item >= day:
            return item
    return None


def next_session_after(dates: list[date], day: date) -> date | None:
    for item in dates:
        if item > day:
            return item
    return None


def fill_1800(state, day: date, ahead: int, opens: dict[date, int]):
    known = state["close_i"].get(day)
    pos = state["pos"].get(day)
    if known is None or pos is None or pos + ahead >= len(state["session_dates"]):
        return None
    entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
    exit_i = state["close_i"].get(state["session_dates"][pos + ahead])
    if entry_ts is None or exit_i is None:
        return None
    entry_i = int(state["index"].searchsorted(entry_ts))
    if exit_i <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    gross = float(state["close"][exit_i] - entry_px)
    return trade(day, gross, entry_px), state["session_dates"][pos + ahead]


def fill_0930(state, day: date, ahead: int, opens: dict[date, int]):
    entry_day = next_session_after(state["session_dates"], day)
    if entry_day is None:
        return None
    pos = state["pos"].get(entry_day)
    entry_i = opens.get(entry_day)
    if pos is None or entry_i is None or pos + ahead >= len(state["session_dates"]):
        return None
    exit_i = state["close_i"].get(state["session_dates"][pos + ahead])
    if exit_i is None or exit_i <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    gross = float(state["close"][exit_i] - entry_px)
    return trade(entry_day, gross, entry_px), state["session_dates"][pos + ahead]


def build_signals(state, signal_days: dict[str, list[date]]) -> dict[str, list[dict]]:
    book = {name: [] for name in NEW_CELLS}
    opens = open_map(state)
    for name in NEW_CELLS:
        exit_day = date(1900, 1, 1)
        for day in signal_days[name]:
            if name == "cot_crowded_short_long":
                day = first_session_on_or_after(state["session_dates"], day)
                if day is None:
                    continue
            if day <= exit_day:
                continue
            if name == "curve_uninversion_long":
                filled = fill_0930(state, day, HOLDS[name], opens)
            else:
                filled = fill_1800(state, day, HOLDS[name], opens)
            if filled is None:
                continue
            row, exit_day = filled
            book[name].append(row)
    return book


def pf_clears(stats: dict) -> bool:
    pf = stats.get("profit_factor")
    if pf is None:
        return stats.get("avg_loss") is None and (stats.get("expectancy") or 0) > 0 and (stats.get("trades") or 0) > 0
    return pf > 1.5


def bar_clears(stats: dict) -> bool:
    ci = stats.get("expectancy_ci") or [None, None]
    return bool(
        (stats.get("trades") or 0) >= 15
        and ci[0] is not None and ci[0] > 0
        and pf_clears(stats)
        and (stats.get("years_positive") or 0) > 0.60
    )


def main() -> None:
    if len(NEW_CELLS) != len(set(NEW_CELLS)):
        raise RuntimeError("duplicate rule")
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, "hold", HOLDS[name], flush=True)
    print("CONFIRM USATECH same five rules, same clocks", flush=True)
    signal_days = features()
    ranges = signal_days.pop("_ranges")
    print("DATA", json.dumps(ranges), flush=True)
    for name in NEW_CELLS:
        print(" signals", name, len(signal_days[name]), flush=True)
    usa = load_bars(symbol_paths("usa500"))
    tech = load_bars(symbol_paths("usatech"))
    print("BARS", usa.index[-1].isoformat(), tech.index[-1].isoformat(), flush=True)
    state = prepare_paths(usa)
    book = build_signals(state, signal_days)
    tech_book = build_signals(prepare_paths(tech), signal_days)
    print("prior family", flush=True)
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
    prior.update(lead_lag(usa, tech))
    prior.update(opening_fade(usa))
    prior.update(weekly_book(state))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= test_end]
    names, cols, rows = [], [], []
    for name, trades in prior.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    passed = []
    for name in NEW_CELLS:
        trades = book[name]
        test = summarize(keep(trades, TEST_START, test_end), COST)
        stress = summarize(keep(trades, TEST_START, test_end), COST * 2)
        val = summarize(keep(trades, VAL_START, VAL_END), COST)
        train = summarize(keep(trades, TRAIN_START, TRAIN_END), COST)
        rep = tech_book[name]
        rep_stats = summarize(net_of_fraction(keep(rep, TEST_START, test_end), 0.0004), 0.0)
        row = {
            "name": name,
            "entry": "09:30 ET next cash session" if name == "curve_uninversion_long" else "18:00 ET",
            "exit": f"15:55 ET close {HOLDS[name]} cash sessions later",
            "test": test,
            "test_2x": slim(stress),
            "validation": slim(val),
            "train": slim(train),
            "replication_usatech_2x": slim(rep_stats),
            "spx_bar": bar_clears(stress),
            "replication_bar": bar_clears(rep_stats),
        }
        rows.append(row)
        names.append(name)
        cols.append(pnl_on_days(trades, calendar, COST))
        print(name, "n", test["trades"], "win", test["win_rate"], "exp2", stress["expectancy"], stress["expectancy_ci"], "pf2", stress["profit_factor"], "years", stress["years_positive"], "rep_n", rep_stats["trades"], "rep_exp", rep_stats["expectancy"], flush=True)
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
        "success_bar": "2x expectancy CI lower > 0, profit factor > 1.5 after 2x costs, more than 60% of active test years profitable, at least 15 test trades, reality p<0.05 and DSR>=0.95 on the full matrix, and the same bar on USATECH at a 0.04% round-trip cost. Time exits only.",
        "blocked_sources": {
            "cboe_put_call": "cdn.cboe.com equitypc.csv, indexpc.csv and totalpc.csv end on 2019-10-04. The current daily statistics page has no public CSV.",
            "fred": "fred.stlouisfed.org timed out. WALCL, RRPONTSYD, WTREGEN, BAMLH0A0HYM2 and NFCI were not used. The 10y-2y spread was rebuilt from Treasury.gov.",
            "aaii": "www.aaii.com returned 403.",
        },
        "data_ranges": ranges,
        "futures_last_bar": usa.index[-1].isoformat(),
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
    Path("artifacts/rare_setups/run20.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed, "BEST", names[best], reality.get("p_value"), round(float(dsr.get("dsr") or 0), 4), "N", len(names))


if __name__ == "__main__":
    main()
