"""Run 16. This list is fixed before any result is computed.

Do not append a cell after seeing a number. The new family is three
blocks that were not the rules in runs 11-15:

1. Time-of-day drift on USA500 5-minute bids. A 30-minute or session
   window is bought at the open of the first 5-minute bar and sold at
   the open of the bar that starts when the window ends. Full 1-minute
   history is not on disk; the 5-minute open at a clock is the same
   print as the first 1-minute open at that clock.
2. Calendar longs entered at 18:00 ET, which is a different fill from
   the cash-open calendar tests in run 12. CPI dates are the BLS
   schedule below, not a guessed second-week rule.
3. 60-minute Donchian and Keltner breakouts with a volatility filter
   and a trailing stop. These report win rate and payoff. They are not
   the 5-minute, six-hour-exit grid from the earlier 24-hour study.

The confirmatory rule is one pre-specified replication, not a search.
It is RSI(2)<5, with RSP beating SPY or IWM beating SPY, entered at
18:00 and exited at +0.5% within three sessions. The sample is locked
before that rule's trades are built: USATECH 5-minute bids over
2022-2026 if that file is already on disk, otherwise USA500 over
2012-2017. Neither sample is the USA500 2022-2026 window that
identified the finalist.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check
from rare_setups_run12 import TEST_END, TEST_START, new_tradebook, old_tradebook, pnl_on_days
from rare_setups_run13 import VAL_END, VAL_START, entry_stamp, live_bar, load_5m
from rare_setups_run14 import prepare_paths
from rare_setups_run15 import as_of, build_book, cross_asset, path_target, target_book
from rare_setups_study import COST, FOMC, build_daily, metrics, third_fridays

TRAIN_START = date(2012, 1, 1)
TRAIN_END = date(2017, 12, 31)
SEASON = (
    "asia_1800_0200",
    "london_0300_0800",
    "asia_monday",
    "asia_friday",
    "london_monday",
    "london_friday",
    "rth_1030_1100",
    "rth_1400_1430",
)
CALENDAR = (
    "tom_1800",
    "pre_holiday_1800",
    "fomc_1800",
    "cpi_1800",
    "opex_monday_1800",
    "monday_1800",
    "friday_1800",
)
TREND = (
    "donchian20_long_vol_trail3",
    "donchian20_short_vol_trail3",
    "donchian55_long_vol_trail3",
    "donchian55_short_vol_trail3",
    "keltner20_long_vol_trail2",
    "keltner20_short_vol_trail2",
)
NEW_CELLS = SEASON + CALENDAR + TREND
CONFIRM_NAME = "confirm_rsi2_rsp_or_iwm_t0.005_d3"
# BLS "Consumer Price Index" rows from https://www.bls.gov/schedule/{year}/home.htm.
# 2011 is not on the fetched pages used here. The 2025 page does not list a
# release for the October reference month. 2025-10-24 is the delayed September release.
CPI_TEXT = """
2012-01-19 2012-02-17 2012-03-16 2012-04-13 2012-05-15 2012-06-14
2012-07-17 2012-08-15 2012-09-14 2012-10-16 2012-11-15 2012-12-14
2013-01-16 2013-02-21 2013-03-15 2013-04-16 2013-05-16 2013-06-18
2013-07-16 2013-08-15 2013-09-17 2013-10-30 2013-11-20 2013-12-17
2014-01-16 2014-02-20 2014-03-18 2014-04-15 2014-05-15 2014-06-17
2014-07-22 2014-08-19 2014-09-17 2014-10-22 2014-11-20 2014-12-17
2015-01-16 2015-02-26 2015-03-24 2015-04-17 2015-05-22 2015-06-18
2015-07-17 2015-08-19 2015-09-16 2015-10-15 2015-11-17 2015-12-15
2016-01-20 2016-02-19 2016-03-16 2016-04-14 2016-05-17 2016-06-16
2016-07-15 2016-08-16 2016-09-16 2016-10-18 2016-11-17 2016-12-15
2017-01-18 2017-02-15 2017-03-15 2017-04-14 2017-05-12 2017-06-14
2017-07-14 2017-08-11 2017-09-14 2017-10-13 2017-11-15 2017-12-13
2018-01-12 2018-02-14 2018-03-13 2018-04-11 2018-05-10 2018-06-12
2018-07-12 2018-08-10 2018-09-13 2018-10-11 2018-11-14 2018-12-12
2019-01-11 2019-02-13 2019-03-12 2019-04-10 2019-05-10 2019-06-12
2019-07-11 2019-08-13 2019-09-12 2019-10-10 2019-11-13 2019-12-11
2020-01-14 2020-02-13 2020-03-11 2020-04-10 2020-05-12 2020-06-10
2020-07-14 2020-08-12 2020-09-11 2020-10-13 2020-11-12 2020-12-10
2021-01-13 2021-02-10 2021-03-10 2021-04-13 2021-05-12 2021-06-10
2021-07-13 2021-08-11 2021-09-14 2021-10-13 2021-11-10 2021-12-10
2022-01-12 2022-02-10 2022-03-10 2022-04-12 2022-05-11 2022-06-10
2022-07-13 2022-08-10 2022-09-13 2022-10-13 2022-11-10 2022-12-13
2023-01-12 2023-02-14 2023-03-14 2023-04-12 2023-05-10 2023-06-13
2023-07-12 2023-08-10 2023-09-13 2023-10-12 2023-11-14 2023-12-12
2024-01-11 2024-02-13 2024-03-12 2024-04-10 2024-05-15 2024-06-12
2024-07-11 2024-08-14 2024-09-11 2024-10-10 2024-11-13 2024-12-11
2025-01-15 2025-02-12 2025-03-12 2025-04-10 2025-05-13 2025-06-11
2025-07-15 2025-08-12 2025-09-11 2025-10-24 2025-12-18
2026-01-13 2026-02-13 2026-03-11 2026-04-10 2026-05-12 2026-06-10
2026-07-14 2026-08-12 2026-09-11 2026-10-14 2026-11-10 2026-12-10
"""
CPI = {date.fromisoformat(token) for token in CPI_TEXT.split()}


def _check_calendar() -> None:
    if len(NEW_CELLS) != len(set(NEW_CELLS)) or len(NEW_CELLS) != 21:
        raise RuntimeError("rule list changed")
    if len(CPI) != len(CPI_TEXT.split()):
        raise RuntimeError("duplicate CPI date")
    by_year: dict[int, int] = {}
    for day in CPI:
        by_year[day.year] = by_year.get(day.year, 0) + 1
    for year in range(2012, 2027):
        expected = 11 if year == 2025 else 12
        if by_year.get(year) != expected:
            raise RuntimeError(f"CPI {year} has {by_year.get(year)}")


def trade(day: date, gross: float, entry: float = 0.0) -> dict:
    return {"day": day, "year": day.year, "gross": float(gross), "side": 1, "entry": float(entry)}


def keep(trades, start, end):
    return [row for row in trades if start <= row["day"] <= end]


def summarize(trades, cost: float) -> dict:
    row = metrics(trades, cost)
    return row


def net_of_fraction(trades, fraction: float) -> list[dict]:
    out = []
    for row in trades:
        item = dict(row)
        item["gross"] = row["gross"] - fraction * row["entry"]
        out.append(item)
    return out


def clearly_fails_validation(val: dict) -> bool:
    if val.get("trades", 0) < 10:
        return False
    ci = val.get("expectancy_ci") or [None, None]
    return ci[1] is not None and ci[1] < 0


def family_success(row) -> bool:
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


def confirm_success(stats_1x, stats_2x, single) -> bool:
    wr = stats_1x.get("win_rate")
    wci = stats_1x.get("win_rate_ci") or [None, None]
    ci = stats_1x.get("expectancy_ci") or [None, None]
    ci2 = stats_2x.get("expectancy_ci") or [None, None]
    return bool(
        stats_1x.get("trades", 0) >= 20
        and wr is not None and wr >= 0.70
        and wci[0] is not None and wci[0] > 0.50
        and ci[0] is not None and ci[0] > 0
        and ci2[0] is not None and ci2[0] > 0
        and single["reality_p"] < 0.05
        and single["dsr"] >= 0.95
    )


def stamp_map(index: pd.DatetimeIndex, hour: int, minute: int) -> dict[date, int]:
    mask = (index.hour == hour) & (index.minute == minute)
    found = {}
    for pos in np.flatnonzero(mask):
        found[index[pos].date()] = int(pos)
    return found


def session_for(day: date, session_dates: list[date]) -> date | None:
    if day in session_dates:
        return day
    for item in session_dates:
        if item >= day:
            return item
    return None


def window_book(state) -> dict[str, list[dict]]:
    index = state["index"]
    bars = state["bars"]
    opens = state["open"]
    sessions = set(state["session_dates"])
    clocks = {
        (18, 0): stamp_map(index, 18, 0),
        (2, 0): stamp_map(index, 2, 0),
        (3, 0): stamp_map(index, 3, 0),
        (8, 0): stamp_map(index, 8, 0),
        (10, 30): stamp_map(index, 10, 30),
        (11, 0): stamp_map(index, 11, 0),
        (14, 0): stamp_map(index, 14, 0),
        (14, 30): stamp_map(index, 14, 30),
    }
    specs = {
        "asia_1800_0200": ((18, 0), (2, 0), 1, None),
        "london_0300_0800": ((3, 0), (8, 0), 0, None),
        "asia_monday": ((18, 0), (2, 0), 1, 0),
        "asia_friday": ((18, 0), (2, 0), 1, 4),
        "london_monday": ((3, 0), (8, 0), 0, 0),
        "london_friday": ((3, 0), (8, 0), 0, 4),
        "rth_1030_1100": ((10, 30), (11, 0), 0, None),
        "rth_1400_1430": ((14, 0), (14, 30), 0, None),
    }
    book = {name: [] for name in SEASON}
    for name, (start, end, day_shift, weekday) in specs.items():
        for day, start_i in clocks[start].items():
            start_ts = index[start_i]
            if weekday is not None and start_ts.weekday() != weekday:
                continue
            end_day = day + timedelta(days=day_shift) if day_shift else day
            end_i = clocks[end].get(end_day)
            if end_i is None or end_i <= start_i:
                continue
            if not live_bar(bars, start_ts) or not live_bar(bars, index[end_i]):
                continue
            booked = day if day in sessions else session_for(day, state["session_dates"])
            if booked is None:
                continue
            gross = float(opens[end_i] - opens[start_i])
            book[name].append(trade(booked, gross, float(opens[start_i])))
    return book


def next_close_gross(state, day: date):
    known = state["close_i"].get(day)
    pos = state["pos"].get(day)
    if known is None or pos is None or pos + 1 >= len(state["session_dates"]):
        return None
    entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
    nxt = state["close_i"].get(state["session_dates"][pos + 1])
    if entry_ts is None or nxt is None:
        return None
    entry_i = int(state["index"].searchsorted(entry_ts))
    if nxt <= entry_i:
        return None
    entry_px = float(state["open"][entry_i])
    return trade(day, float(state["close"][nxt] - entry_px), entry_px)


def calendar_book(state) -> dict[str, list[dict]]:
    book = {name: [] for name in CALENDAR}
    dates = state["session_dates"]
    fridays = third_fridays(pd.DatetimeIndex(pd.to_datetime(dates)))
    for i, day in enumerate(dates):
        stamp = pd.Timestamp(day)
        row = next_close_gross(state, day)
        if row is not None:
            if stamp.weekday() == 0:
                book["monday_1800"].append(row)
            if stamp.weekday() == 4:
                book["friday_1800"].append(dict(row))
            if day in FOMC:
                book["fomc_1800"].append(dict(row))
            if day in CPI:
                book["cpi_1800"].append(dict(row))
            if i + 1 < len(dates) and (dates[i + 1] - day).days >= 4:
                book["pre_holiday_1800"].append(dict(row))
        month_end = i + 1 == len(dates) or dates[i + 1].month != day.month
        if month_end and i + 3 < len(dates):
            known = state["close_i"].get(day)
            far = state["close_i"].get(dates[i + 3])
            if known is None or far is None:
                continue
            entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
            if entry_ts is None:
                continue
            entry_i = int(state["index"].searchsorted(entry_ts))
            if far > entry_i:
                entry_px = float(state["open"][entry_i])
                book["tom_1800"].append(trade(day, float(state["close"][far] - entry_px), entry_px))
        if day in fridays and i >= 1:
            monday = None
            for back in range(i - 1, max(-1, i - 5), -1):
                if dates[back] < day and (day - dates[back]).days <= 4 and pd.Timestamp(dates[back]).weekday() == 0:
                    monday = dates[back]
                    break
            if monday is None:
                continue
            known = state["close_i"].get(monday)
            friday_close = state["close_i"].get(day)
            if known is None or friday_close is None:
                continue
            entry_ts = entry_stamp("18:00", state["index"][known] + pd.Timedelta(minutes=5), state["clocks"], state["bars"])
            if entry_ts is None:
                continue
            entry_i = int(state["index"].searchsorted(entry_ts))
            if friday_close > entry_i:
                entry_px = float(state["open"][entry_i])
                book["opex_monday_1800"].append(trade(monday, float(state["close"][friday_close] - entry_px), entry_px))
    return book


def hourly_bars(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.resample("1h", label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return frame.dropna()


def trend_book(bars: pd.DataFrame) -> dict[str, list[dict]]:
    frame = hourly_bars(bars)
    high = frame["high"].to_numpy(float)
    low = frame["low"].to_numpy(float)
    close = frame["close"].to_numpy(float)
    open_ = frame["open"].to_numpy(float)
    index = frame.index
    prev = frame["close"].shift()
    tr = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - prev).abs(),
        (frame["low"] - prev).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(20).mean().to_numpy(float)
    med = pd.Series(atr).rolling(100).median().to_numpy(float)
    ema = frame["close"].ewm(span=20, adjust=False).mean().to_numpy(float)
    specs = {
        "donchian20_long_vol_trail3": ("don", 20, 1, 3.0),
        "donchian20_short_vol_trail3": ("don", 20, -1, 3.0),
        "donchian55_long_vol_trail3": ("don", 55, 1, 3.0),
        "donchian55_short_vol_trail3": ("don", 55, -1, 3.0),
        "keltner20_long_vol_trail2": ("kel", 20, 1, 2.0),
        "keltner20_short_vol_trail2": ("kel", 20, -1, 2.0),
    }
    book = {name: [] for name in TREND}
    n = len(frame)
    for name, (kind, length, side, trail) in specs.items():
        exit_i = -1
        start = max(length + 1, 100)
        for i in range(start, n - 2):
            if i <= exit_i or not np.isfinite(atr[i]) or not np.isfinite(med[i]) or atr[i] <= med[i]:
                continue
            if kind == "don":
                if side == 1 and not close[i] > np.max(high[i - length:i]):
                    continue
                if side == -1 and not close[i] < np.min(low[i - length:i]):
                    continue
            else:
                band = ema[i] + side * 2 * atr[i]
                if side == 1 and not close[i] > band:
                    continue
                if side == -1 and not close[i] < band:
                    continue
            entry_i = i + 1
            entry_px = open_[entry_i]
            risk = atr[i]
            stop = entry_px - side * 2 * risk
            extreme = entry_px
            last = min(n - 1, entry_i + 120)
            fill = close[last]
            exit_at = last
            for j in range(entry_i, last + 1):
                if side == 1 and low[j] <= stop:
                    fill = open_[j] if open_[j] < stop else stop
                    exit_at = j
                    break
                if side == -1 and high[j] >= stop:
                    fill = open_[j] if open_[j] > stop else stop
                    exit_at = j
                    break
                if side == 1:
                    extreme = max(extreme, high[j])
                    stop = max(stop, extreme - trail * risk)
                else:
                    extreme = min(extreme, low[j])
                    stop = min(stop, extreme + trail * risk)
                if kind == "don" and j >= entry_i + 10:
                    if side == 1 and close[j] < np.min(low[j - 10:j]):
                        fill = close[j]
                        exit_at = j
                        break
                    if side == -1 and close[j] > np.max(high[j - 10:j]):
                        fill = close[j]
                        exit_at = j
                        break
                if kind == "kel" and ((side == 1 and close[j] < ema[j]) or (side == -1 and close[j] > ema[j])):
                    fill = close[j]
                    exit_at = j
                    break
            exit_i = exit_at
            gross = side * (fill - entry_px)
            book[name].append(trade(index[exit_at].date(), gross, entry_px))
    return book


def confirm_trades(state, cross: pd.DataFrame) -> list[dict]:
    rows = []
    flag = state["flags"]["rsi2_lt5"]
    index = state["index"]
    for stamp in flag.index[flag.fillna(False)]:
        day = stamp.date()
        if not (as_of(cross["rsp_rel"], day) > 0 or as_of(cross["iwm_rel"], day) > 0):
            continue
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
        gross = path_target(state, entry_i, entry_px, 0.005, far)
        rows.append(trade(day, gross, entry_px))
    return rows


def pack(name, test, stress, val, train) -> dict:
    return {
        "name": name,
        "test": test,
        "test_2x": {
            "expectancy": stress.get("expectancy"),
            "expectancy_ci": stress.get("expectancy_ci"),
            "win_rate": stress.get("win_rate"),
            "profit_factor": stress.get("profit_factor"),
            "avg_win": stress.get("avg_win"),
            "avg_loss": stress.get("avg_loss"),
        },
        "validation": {k: val.get(k) for k in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss")},
        "train": {k: train.get(k) for k in ("trades", "win_rate", "expectancy", "expectancy_ci", "profit_factor")},
        "validation_failed": clearly_fails_validation(val),
        "payoff": {
            "avg_win": test.get("avg_win"),
            "avg_loss": test.get("avg_loss"),
            "profit_factor": test.get("profit_factor"),
            "years_positive": test.get("years_positive"),
            "years": test.get("years"),
        },
    }


def main() -> None:
    _check_calendar()
    print("PRE-REGISTERED", len(NEW_CELLS))
    for name in NEW_CELLS:
        print(" -", name, flush=True)
    print("CONFIRM", CONFIRM_NAME, flush=True)
    tech_files = [path for path in Path("/tmp/rare_data/m5").glob("usatech*.csv") if path.stat().st_size > 1_000_000 and ".part" not in path.name]
    if tech_files:
        confirm_sample = "USATECH 5-minute bid, test window 2022-01-01 through 2026-11-11. Round-trip cost is 0.02% of the entry price (about one SPX point when the index is 5000); 2x is 0.04%."
        confirm_path = tech_files[0]
    else:
        confirm_sample = "USA500 5-minute bid, 2012-01-01 through 2017-12-31. This train window was not the sample that identified the finalist. Cost is 1.0 index point round trip, and 2.0 at the stress."
        confirm_path = None
    print("CONFIRM SAMPLE LOCKED", confirm_sample, flush=True)
    usa_path = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))[0]
    bars = load_5m(usa_path)
    state = prepare_paths(bars)
    book = {}
    book.update(window_book(state))
    book.update(calendar_book(state))
    book.update(trend_book(bars))
    missing = [name for name in NEW_CELLS if name not in book]
    if missing:
        raise RuntimeError(str(missing))
    print("prior family", flush=True)
    yahoo = build_daily(Path("/tmp/rare_data/daily"))[0]
    prior = old_tradebook(yahoo, usa_path)
    prior.update(new_tradebook(yahoo, bars))
    prior.update(target_book(state))
    cross = cross_asset(Path("/tmp/rare_data/daily"))
    prior.update(build_book(state, cross, state["close"]))
    calendar = [stamp.date() for stamp in yahoo.index if TEST_START <= stamp.date() <= TEST_END]
    names, cols, rows = [], [], []
    for name, trades in prior.items():
        names.append(f"prior::{name}")
        cols.append(pnl_on_days(trades, calendar, COST))
    for name in NEW_CELLS:
        trades = book[name]
        test = summarize(keep(trades, TEST_START, TEST_END), COST)
        stress = summarize(keep(trades, TEST_START, TEST_END), COST * 2)
        val = summarize(keep(trades, VAL_START, VAL_END), COST)
        train = summarize(keep(trades, TRAIN_START, TRAIN_END), COST)
        rows.append(pack(name, test, stress, val, train))
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
        row["meets_success_bar"] = family_success(row)
        if row["meets_success_bar"]:
            passed.append(row["name"])
    if confirm_path is not None:
        confirm_state = prepare_paths(load_5m(confirm_path))
        confirm_rows = confirm_trades(confirm_state, cross)
        sample_rows = keep(confirm_rows, TEST_START, TEST_END)
        stats = summarize(net_of_fraction(sample_rows, 0.0002), 0.0)
        stress = summarize(net_of_fraction(sample_rows, 0.0004), 0.0)
        daily = pnl_on_days(net_of_fraction(sample_rows, 0.0002), calendar, 0.0)
    else:
        confirm_rows = confirm_trades(state, cross)
        sample_rows = keep(confirm_rows, TRAIN_START, TRAIN_END)
        stats = summarize(sample_rows, COST)
        stress = summarize(sample_rows, COST * 2)
        train_days = [stamp.date() for stamp in yahoo.index if TRAIN_START <= stamp.date() <= TRAIN_END]
        daily = pnl_on_days(sample_rows, train_days, COST)
    daily = daily.reshape(-1, 1) if daily.size else np.zeros((0, 1))
    if daily.shape[0] >= 10:
        single_rc = whites_reality_check(daily, float(daily.mean()))
        single_dsr = deflated_sharpe_of(daily[:, 0], 0.0)
        conservative = deflated_sharpe_of(daily[:, 0], sr_star)
    else:
        single_rc = {"p_value": 1.0, "survives": False}
        single_dsr = {"dsr": 0.0, "survives": False}
        conservative = {"dsr": 0.0, "survives": False}
    single = {"reality_p": single_rc["p_value"], "dsr": single_dsr["dsr"], "survives": bool(single_rc.get("survives") and single_dsr.get("survives"))}
    confirm_pass = confirm_success(stats, stress, single)
    if confirm_pass:
        passed.append(CONFIRM_NAME)
    payload = {
        "preregistered": list(NEW_CELLS),
        "confirmatory_rule": {
            "name": CONFIRM_NAME,
            "definition": "RSI(2)<5 on the replication instrument's cash session, and RSP daily return above SPY or IWM daily return above SPY. Enter 18:00 ET. Exit at +0.5% or at the close three sessions later.",
            "sample": confirm_sample,
            "test": stats,
            "test_2x": {k: stress.get(k) for k in ("trades", "win_rate", "win_rate_ci", "expectancy", "expectancy_ci", "profit_factor", "avg_win", "avg_loss")},
            "single_test": single,
            "conservative_dsr_vs_full_family": conservative,
            "passes_confirmatory_bar": confirm_pass,
        },
        "new_cells": len(NEW_CELLS),
        "matrix_rules": len(names),
        "run13_timing_cells_not_recomputed": 39,
        "family_total_with_run13": len(names) + 39,
        "walk_forward": "Parameters stay fixed. Train 2012-2017, validation 2018-2021, and test 2022-2026 are all stored. Nothing is refit.",
        "availability": {
            "usa500_5m": "Dukascopy bid from 2011-09-18. One-minute history for this span is not on disk. Window fills use the 5-minute open at the clock.",
            "usatech_5m": confirm_sample,
            "cpi": "BLS schedule pages for 2012-2026. No 2011 dates. The 2025 pages omit the October reference-month CPI.",
            "fomc": "Decision dates already listed in rare_setups_study.FOMC. Entry is 18:00 ET after the afternoon decision.",
            "holiday": "A pre-holiday gap is four or more calendar days to the next cash session, so a normal weekend is not a holiday.",
        },
        "success_bar": "Family cells need test win>=70%, win CI lower>50%, expectancy CI lower>0 at 1x and 2x, >=20 test trades, reality p<0.05 and DSR>=0.95 on the full matrix, and validation not entirely below zero. The confirmatory rule uses the same trade bar on its locked sample and a single-test reality check and DSR (N=1). The full-family DSR on that sample is reported beside it.",
        "rows": rows,
        "any_meets_success_bar": bool(passed),
        "passed": passed,
        "best_mean_rule": names[best],
        "reality_check_best": reality,
        "deflated_sharpe_best": {k: v for k, v in dsr.items() if k != "trial_sharpes"},
        "live_default": "legacy",
    }
    Path("artifacts/rare_setups/run16.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print("ANY", bool(passed), passed)
    print("BEST", names[best], reality.get("p_value"), round(dsr.get("dsr", 0), 4), "N", len(names))
    print("CONFIRM", stats.get("trades"), stats.get("win_rate"), stats.get("expectancy"), single, "pass", confirm_pass)


if __name__ == "__main__":
    main()
