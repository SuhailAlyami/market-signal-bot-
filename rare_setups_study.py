"""Rare SPX setups. The rule list is fixed before the run.

Parameters are not searched on the evaluation years. One RSI(2) variant
picks its threshold each year from {5, 10} using only earlier years; both
values count toward the multiple-testing total.

Costs are 0.5 index point per side (1 point round trip). The 2x column
charges 1 point per side. A rule is READY only if the out-of-sample sample
has at least 30 trades, the expectancy interval at both costs lies above
zero, the win-rate interval lies above 50%, profit factor exceeds 1.3,
more than 60% of active years are profitable, and both the reality check
and the deflated Sharpe clear their bars.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from confirm_entry_study import deflated_sharpe, deflated_sharpe_of, whites_reality_check

COST = 1.0  # round trip, 0.5 per side
OOS_START = date(2008, 1, 1)
SECTORS = ("XLK", "XLF", "XLE", "XLV", "XLI", "XLP", "XLU", "XLY")
# Second day of each scheduled meeting. 2015-2022 from the public historical
# list; 2023-2026 from the Federal Reserve calendar.
FOMC = {
    date(2015, 1, 28), date(2015, 3, 18), date(2015, 4, 29), date(2015, 6, 17), date(2015, 7, 29), date(2015, 9, 17), date(2015, 10, 28), date(2015, 12, 16),
    date(2016, 1, 27), date(2016, 3, 16), date(2016, 4, 27), date(2016, 6, 15), date(2016, 7, 27), date(2016, 9, 21), date(2016, 11, 2), date(2016, 12, 14),
    date(2017, 2, 1), date(2017, 3, 15), date(2017, 5, 3), date(2017, 6, 14), date(2017, 7, 26), date(2017, 9, 20), date(2017, 11, 1), date(2017, 12, 13),
    date(2018, 1, 31), date(2018, 3, 21), date(2018, 5, 2), date(2018, 6, 13), date(2018, 8, 1), date(2018, 9, 26), date(2018, 11, 8), date(2018, 12, 19),
    date(2019, 1, 30), date(2019, 3, 20), date(2019, 5, 1), date(2019, 6, 19), date(2019, 7, 31), date(2019, 9, 18), date(2019, 10, 30), date(2019, 12, 11),
    date(2020, 1, 29), date(2020, 3, 18), date(2020, 4, 29), date(2020, 6, 10), date(2020, 7, 29), date(2020, 9, 16), date(2020, 11, 5), date(2020, 12, 16),
    date(2021, 1, 27), date(2021, 3, 17), date(2021, 4, 28), date(2021, 6, 16), date(2021, 7, 28), date(2021, 9, 22), date(2021, 11, 3), date(2021, 12, 15),
    date(2022, 1, 26), date(2022, 3, 16), date(2022, 5, 4), date(2022, 6, 15), date(2022, 7, 27), date(2022, 9, 21), date(2022, 11, 2), date(2022, 12, 14),
    date(2023, 2, 1), date(2023, 3, 22), date(2023, 5, 3), date(2023, 6, 14), date(2023, 7, 26), date(2023, 9, 20), date(2023, 11, 1), date(2023, 12, 13),
    date(2024, 1, 31), date(2024, 3, 20), date(2024, 5, 1), date(2024, 6, 12), date(2024, 7, 31), date(2024, 9, 18), date(2024, 11, 7), date(2024, 12, 18),
    date(2025, 1, 29), date(2025, 3, 19), date(2025, 5, 7), date(2025, 6, 18), date(2025, 7, 30), date(2025, 9, 17), date(2025, 10, 29), date(2025, 12, 10),
    date(2026, 1, 28), date(2026, 3, 18), date(2026, 4, 29), date(2026, 6, 17), date(2026, 7, 29), date(2026, 9, 16), date(2026, 10, 28), date(2026, 12, 9),
}


def load_daily(folder: Path, name: str) -> pd.DataFrame:
    frame = pd.read_csv(folder / f"{name}.csv", index_col=0, parse_dates=True)
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.rename(columns={col: col.capitalize() for col in frame.columns})
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    frame = frame.sort_index()
    return frame[~frame.index.duplicated(keep="last")]


def rsi(close: pd.Series, length: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def wilson(wins: int, n: int) -> list[float] | None:
    if n <= 0:
        return None
    z = 1.959963984540054
    p = wins / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [round(float((centre - margin) / den), 4), round(float((centre + margin) / den), 4)]


def third_fridays(index: pd.DatetimeIndex) -> set[date]:
    found = set()
    for stamp in index:
        if stamp.weekday() == 4 and 15 <= stamp.day <= 21:
            found.add(stamp.date())
    return found


def first_fridays(index: pd.DatetimeIndex) -> set[date]:
    return {stamp.date() for stamp in index if stamp.weekday() == 4 and stamp.day <= 7}


def build_daily(folder: Path) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    gspc = load_daily(folder, "GSPC")
    frame = pd.DataFrame(index=gspc.index)
    frame["open"] = gspc["Open"]
    frame["high"] = gspc["High"]
    frame["low"] = gspc["Low"]
    frame["close"] = gspc["Close"]
    spy = load_daily(folder, "SPY")
    extra = {}
    for name in ("VIX", "VIX3M", "TNX", "DXYNYB", "JPYX", "SPY"):
        src = "DX-YNYB" if name == "DXYNYB" else name
        # files were saved with punctuation stripped
    mapping = {
        "VIX": "VIX", "VIX3M": "VIX3M", "TNX": "TNX", "DXY": "DX-YNYB", "JPY": "JPYX", "SPY": "SPY",
    }
    # actual filenames from the downloader
    files = {path.stem: path for path in folder.glob("*.csv")}
    def col(stem_options, field="Close"):
        for stem in stem_options:
            if stem in files:
                data = load_daily(folder, stem)
                return data[field].reindex(frame.index)
        return pd.Series(np.nan, index=frame.index)
    frame["vix"] = col(["VIX"])
    frame["vix3m"] = col(["VIX3M"])
    frame["tnx"] = col(["TNX"])
    frame["dxy"] = col(["DX-YNYB", "DXYNYB"])
    frame["jpy"] = col(["JPYX", "JPY"])
    frame["spy_open"] = col(["SPY"], "Open")
    frame["spy_close"] = col(["SPY"], "Close")
    sectors = []
    for name in SECTORS:
        series = col([name])
        sectors.append(series > series.rolling(20).mean())
    frame["sector_above"] = pd.concat(sectors, axis=1).mean(axis=1)
    frame["ret"] = frame["close"].pct_change()
    frame["sma20"] = frame["close"].rolling(20).mean()
    tr = pd.concat([
        frame["high"] - frame["low"],
        (frame["high"] - frame["close"].shift()).abs(),
        (frame["low"] - frame["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    frame["atr"] = tr.rolling(14).mean()
    frame["rsi2"] = rsi(frame["close"], 2)
    frame["gap"] = frame["open"] / frame["close"].shift() - 1
    frame["jpy_ret"] = frame["jpy"].pct_change()
    frame["dxy_ret"] = frame["dxy"].pct_change()
    frame["tnx_chg"] = frame["tnx"].diff()
    frame["vix_ret"] = frame["vix"].pct_change()
    return frame, {"spy": spy}


def daily_rules(frame: pd.DataFrame) -> dict[str, pd.Series]:
    """Side at the decision bar. Trade is the next open-to-close unless named overnight or hold-close."""
    idx = frame.index
    opex = third_fridays(idx)
    nfp = first_fridays(idx)
    fomc = {pd.Timestamp(day) for day in FOMC}
    prev_close = frame["close"].shift()
    rules = {}
    rules["overnight_all"] = pd.Series(1, index=idx)
    rules["overnight_contango"] = ((frame["vix"] < frame["vix3m"]) & (frame["vix"] <= 20)).astype(float).where(frame["vix"].notna(), 0)
    rules["overnight_contango"] = rules["overnight_contango"].where(rules["overnight_contango"] == 1, 0)
    tom = []
    for i, stamp in enumerate(idx):
        nxt = idx[i + 1] if i + 1 < len(idx) else None
        last = i + 1 == len(idx) or idx[i + 1].month != stamp.month
        first = nxt is not None and nxt.day <= 3 and (stamp.month != nxt.month or stamp.day <= 3)
        tom.append(1 if last or (nxt is not None and nxt.month != stamp.month) or stamp.day <= 2 else 0)
    rules["overnight_tom"] = pd.Series(tom, index=idx)
    rules["rsi2_long_5"] = (frame["rsi2"] < 5).astype(int)
    rules["rsi2_short_95"] = (frame["rsi2"] > 95).astype(int) * -1
    rules["stretch_long"] = (frame["close"] < frame["sma20"] - 2.5 * frame["atr"]).astype(int)
    rules["stretch_short"] = (frame["close"] > frame["sma20"] + 2.5 * frame["atr"]).astype(int) * -1
    gap = frame["gap"]
    rules["gap_fade"] = np.where(gap >= 0.006, -1, np.where(gap <= -0.006, 1, 0))
    trend_up = prev_close > frame["sma20"].shift()
    go = (gap.abs() >= 0.004) & (np.sign(gap) == np.where(trend_up, 1, -1)) & (frame["vix"] < 18)
    rules["gap_go"] = pd.Series(np.where(go, np.sign(gap), 0), index=idx)
    back = (frame["vix"] > frame["vix3m"]) & (frame["ret"] > 0.005) & (frame["vix_ret"] > 0)
    rules["vix_backwardation_short"] = back.astype(int) * -1
    rules["usdjpy_down_short"] = (frame["jpy_ret"] <= -0.01).astype(int) * -1
    rules["dxy_up_short"] = (frame["dxy_ret"] >= 0.008).astype(int) * -1
    rules["tnx_spike_short"] = (frame["tnx_chg"] >= 0.10).astype(int) * -1
    rules["nfp_gap_fade"] = pd.Series(np.where(idx.map(lambda s: s.date() in nfp) & (gap.abs() >= 0.004), -np.sign(gap), 0), index=idx)
    prev_day = idx.to_series().shift(-1)
    rules["opex_thu_fri"] = pd.Series([1 if (stamp + pd.Timedelta(days=1)).date() in opex or (i + 1 < len(idx) and idx[i + 1].date() in opex) else 0 for i, stamp in enumerate(idx)], index=idx)
    rules["fomc_into_close"] = pd.Series([1 if i + 1 < len(idx) and idx[i + 1].normalize() in fomc else 0 for i in range(len(idx))], index=idx)
    down5 = (frame["close"] < frame["close"].shift()).rolling(5).sum() == 5
    up5 = (frame["close"] > frame["close"].shift()).rolling(5).sum() == 5
    rules["consec5_long"] = down5.astype(int)
    rules["consec5_short"] = up5.astype(int) * -1
    rules["breadth_washout"] = ((frame["sector_above"] <= 0.25) & (frame["close"] < frame["sma20"])).astype(int)
    # Trade style: overnight uses close->next open. Gap/day rules use same-day open->close
    # and the signal is known at the open (gap) or at the prior close (rsi, stretch, calendar).
    return {name: pd.Series(series, index=idx).fillna(0).astype(int) for name, series in rules.items()}


OVERNIGHT = {"overnight_all", "overnight_contango", "overnight_tom", "opex_thu_fri", "fomc_into_close"}
# opex and fomc are close-to-next-close, handled separately
CLOSE_TO_CLOSE = {"opex_thu_fri", "fomc_into_close"}


def trades_from_side(frame: pd.DataFrame, side: pd.Series, kind: str) -> list[dict]:
    rows = []
    opens = frame["open"].to_numpy()
    closes = frame["close"].to_numpy()
    dates = frame.index
    values = side.to_numpy()
    for i, sgn in enumerate(values):
        if sgn == 0 or i + 1 >= len(frame):
            continue
        if dates[i].date() < OOS_START and kind != "intraday":
            continue
        if kind == "overnight":
            gross = sgn * (opens[i + 1] - closes[i])
            day = dates[i + 1].date()
        elif kind == "closeclose":
            gross = sgn * (closes[i + 1] - closes[i])
            day = dates[i + 1].date()
        else:
            # Signal known at prior close, filled next open, exited that close.
            if dates[i].date() < OOS_START:
                continue
            gross = sgn * (closes[i] - opens[i])
            day = dates[i].date()
            # For gap rules the signal is on the same bar as the open. The side
            # series is aligned to that bar, so use bar i, not i+1.
        rows.append({"day": day, "year": day.year, "gross": float(gross), "side": int(sgn)})
    return rows


def same_bar_trades(frame: pd.DataFrame, side: pd.Series) -> list[dict]:
    rows = []
    for stamp, sgn in side.items():
        if sgn == 0 or stamp.date() < OOS_START:
            continue
        gross = int(sgn) * (float(frame.at[stamp, "close"]) - float(frame.at[stamp, "open"]))
        rows.append({"day": stamp.date(), "year": stamp.year, "gross": float(gross), "side": int(sgn)})
    return rows


def next_open_trades(frame: pd.DataFrame, side: pd.Series) -> list[dict]:
    """Signal at close i, enter next open, exit that close."""
    rows = []
    idx = frame.index
    for i, stamp in enumerate(idx[:-1]):
        sgn = int(side.iloc[i])
        if sgn == 0:
            continue
        nxt = idx[i + 1]
        if nxt.date() < OOS_START:
            continue
        gross = sgn * (float(frame.at[nxt, "close"]) - float(frame.at[nxt, "open"]))
        rows.append({"day": nxt.date(), "year": nxt.year, "gross": gross, "side": sgn})
    return rows


def overnight_trades(frame: pd.DataFrame, side: pd.Series) -> list[dict]:
    rows = []
    idx = frame.index
    for i, stamp in enumerate(idx[:-1]):
        sgn = int(side.iloc[i])
        if sgn == 0:
            continue
        nxt = idx[i + 1]
        if nxt.date() < OOS_START:
            continue
        gross = sgn * (float(frame.at[nxt, "open"]) - float(frame.at[stamp, "close"]))
        rows.append({"day": nxt.date(), "year": nxt.year, "gross": gross, "side": sgn})
    return rows


def closeclose_trades(frame: pd.DataFrame, side: pd.Series) -> list[dict]:
    rows = []
    idx = frame.index
    for i, stamp in enumerate(idx[:-1]):
        sgn = int(side.iloc[i])
        if sgn == 0:
            continue
        nxt = idx[i + 1]
        if nxt.date() < OOS_START:
            continue
        gross = sgn * (float(frame.at[nxt, "close"]) - float(frame.at[stamp, "close"]))
        rows.append({"day": nxt.date(), "year": nxt.year, "gross": gross, "side": sgn})
    return rows


def metrics(trades: list[dict], cost: float = COST) -> dict:
    if not trades:
        return {"trades": 0, "trades_per_month": 0, "win_rate": None, "win_rate_ci": None,
                "avg_win": None, "avg_loss": None, "expectancy": None, "expectancy_ci": None,
                "profit_factor": None, "max_drawdown": None, "years_positive": None, "years": []}
    pnls = np.array([item["gross"] - cost for item in trades])
    wins = pnls[pnls > 0]
    losses = pnls[pnls < 0]
    months = sorted({(item["day"].year, item["day"].month) for item in trades})
    span_months = max(1, (trades[-1]["day"].year - trades[0]["day"].year) * 12 + trades[-1]["day"].month - trades[0]["day"].month + 1)
    by_month: dict[tuple, list[float]] = {}
    by_year: dict[int, list[float]] = {}
    for item, pnl in zip(trades, pnls):
        by_month.setdefault((item["day"].year, item["day"].month), []).append(float(pnl))
        by_year.setdefault(item["year"], []).append(float(pnl))
    keys = list(by_month)
    rng = np.random.default_rng(16)
    samples = []
    for _ in range(500):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        pool = [value for k in pick for value in by_month[keys[k]]]
        if pool:
            samples.append(float(np.mean(pool)))
    ci = None if len(samples) < 20 else [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]
    pf = None
    if losses.size and wins.size:
        pf = round(float(wins.sum() / abs(losses.sum())), 4)
    elif wins.size:
        pf = None
    equity = np.cumsum(pnls)
    dd = float(np.max(np.maximum.accumulate(equity) - equity))
    years = []
    for year in sorted(by_year):
        values = np.array(by_year[year])
        years.append({"year": year, "trades": int(len(values)), "total": round(float(values.sum()), 2), "win_rate": round(float(np.mean(values > 0)), 4)})
    active = [row for row in years if row["trades"]]
    positive = sum(1 for row in active if row["total"] > 0)
    return {
        "trades": int(len(pnls)),
        "trades_per_month": round(len(pnls) / span_months, 3),
        "win_rate": round(float(np.mean(pnls > 0)), 4),
        "win_rate_ci": wilson(int((pnls > 0).sum()), len(pnls)),
        "avg_win": round(float(wins.mean()), 4) if wins.size else None,
        "avg_loss": round(float(losses.mean()), 4) if losses.size else None,
        "expectancy": round(float(pnls.mean()), 4),
        "expectancy_ci": ci,
        "profit_factor": pf,
        "max_drawdown": round(dd, 4),
        "years_positive": None if not active else round(positive / len(active), 4),
        "years_active": len(active),
        "years": years,
    }


def passes(row: dict, row2: dict, reality: dict, dsr: dict) -> dict:
    reasons = []
    if row["trades"] < 30:
        reasons.append("fewer than 30 out-of-sample trades")
    ci = row.get("expectancy_ci") or [None, None]
    ci2 = row2.get("expectancy_ci") or [None, None]
    wr = row.get("win_rate_ci") or [None, None]
    if not (ci[0] is not None and ci[0] > 0):
        reasons.append("expectancy interval is not above zero")
    if not (ci2[0] is not None and ci2[0] > 0):
        reasons.append("2x-cost expectancy interval is not above zero")
    if not (wr[0] is not None and wr[0] > 0.5):
        reasons.append("win-rate interval is not above 50%")
    if not (row.get("profit_factor") or 0) > 1.3:
        reasons.append("profit factor is not above 1.3")
    if not (row.get("years_positive") or 0) > 0.6:
        reasons.append("not positive in most years")
    if not reality.get("survives"):
        reasons.append("reality check does not clear")
    if not dsr.get("survives"):
        reasons.append("deflated Sharpe is below 0.95")
    return {"promote": not reasons, "reason": "passed the predeclared bars" if not reasons else "; ".join(reasons)}


def walk_forward_rsi(frame: pd.DataFrame) -> list[dict]:
    """Each year, pick RSI(2) < 5 or < 10 from earlier years only, then trade that year."""
    side5 = (frame["rsi2"] < 5).astype(int)
    side10 = (frame["rsi2"] < 10).astype(int)
    trades = []
    years = range(2009, 2027)
    for year in years:
        prior = []
        for threshold, side in ((5, side5), (10, side10)):
            sample = next_open_trades(frame.loc[:f"{year-1}-12-31"], side.loc[:f"{year-1}-12-31"])
            sample = [row for row in sample if row["year"] < year]
            if len(sample) < 15:
                continue
            expectancy = float(np.mean([row["gross"] - COST for row in sample]))
            prior.append((expectancy, threshold, side))
        if not prior:
            continue
        prior.sort(reverse=True)
        chosen = prior[0][2]
        year_trades = [row for row in next_open_trades(frame.loc[f"{year-1}-12-01":f"{year}-12-31"], chosen.loc[f"{year-1}-12-01":f"{year}-12-31"]) if row["year"] == year]
        trades.extend(year_trades)
    return trades


def intraday(path: Path) -> dict[str, list[dict]]:
    if not path.exists():
        return {}
    raw = pd.read_csv(path)
    raw["ts"] = pd.to_datetime(raw["timestamp"], unit="ms", utc=True).dt.tz_convert("America/New_York")
    raw = raw.set_index("ts")
    close = raw["close"].astype(float)
    high = raw["high"].astype(float)
    low = raw["low"].astype(float)
    open_ = raw["open"].astype(float)
    window = 36
    rng = high.rolling(window).max() - low.rolling(window).min()
    rank = rng.rolling(2000, min_periods=500).rank(pct=True)
    prior_high = high.rolling(window).max().shift(1)
    prior_low = low.rolling(window).min().shift(1)
    tight = rank <= 0.05
    fresh_tight = tight & ~tight.shift(1, fill_value=False)
    long_i = np.flatnonzero((fresh_tight & (close > prior_high)).fillna(False).to_numpy())
    short_i = np.flatnonzero((fresh_tight & (close < prior_low)).fillna(False).to_numpy())
    trades = []
    busy = -1
    for i, sgn in sorted([(int(i), 1) for i in long_i] + [(int(i), -1) for i in short_i]):
        if i <= busy or i + 13 >= len(close):
            continue
        if raw.index[i].date() < date(2013, 1, 1):
            continue
        quote = float(open_.iloc[i + 1])
        width = float(rng.iloc[i])
        if not np.isfinite(width) or width <= 0:
            continue
        stop = quote - sgn * width
        target = quote + sgn * width
        exit_price = None
        last = i + 1
        for j in range(i + 1, i + 13):
            last = j
            if sgn > 0 and low.iloc[j] <= stop:
                exit_price = stop
                break
            if sgn < 0 and high.iloc[j] >= stop:
                exit_price = stop
                break
            if sgn > 0 and high.iloc[j] >= target:
                exit_price = target
                break
            if sgn < 0 and low.iloc[j] <= target:
                exit_price = target
                break
        if exit_price is None:
            exit_price = float(close.iloc[last])
        gross = sgn * (exit_price - quote)
        day = raw.index[i + 1].date()
        trades.append({"day": day, "year": day.year, "gross": float(gross), "side": sgn})
        busy = last
    # Last-hour fade after a large up day.
    local = raw.copy()
    local["minute"] = local.index.hour * 60 + local.index.minute
    local["day"] = local.index.date
    fade = []
    for day, chunk in local.groupby("day"):
        rth = chunk[(chunk["minute"] >= 9 * 60 + 30) & (chunk["minute"] < 16 * 60)]
        if len(rth) < 20 or day < date(2013, 1, 1):
            continue
        decision = rth[rth["minute"] <= 15 * 60]
        if decision.empty:
            continue
        op = float(rth["open"].iloc[0])
        px = float(decision["close"].iloc[-1])
        hi = float(decision["high"].max())
        lo = float(decision["low"].min())
        if op <= 0 or hi <= lo:
            continue
        if (px - op) / op < 0.01 or (px - lo) / (hi - lo) < 0.85:
            continue
        exit_bar = rth[rth["minute"] >= 15 * 60 + 55]
        if exit_bar.empty:
            continue
        gross = -1 * (float(exit_bar["close"].iloc[-1]) - px)
        fade.append({"day": day, "year": day.year, "gross": gross, "side": -1})
    return {"compression_break_5m": trades, "last_hour_fade": fade}


def spy_expectancy(frame: pd.DataFrame, side: pd.Series, kind: str) -> dict:
    rows = []
    if kind == "overnight":
        source = overnight_trades(frame.assign(open=frame["spy_open"], close=frame["spy_close"]), side)
    elif kind == "closeclose":
        source = closeclose_trades(frame.assign(close=frame["spy_close"]), side)
    elif kind == "same":
        source = same_bar_trades(frame.assign(open=frame["spy_open"], close=frame["spy_close"]), side)
    else:
        source = next_open_trades(frame.assign(open=frame["spy_open"], close=frame["spy_close"]), side)
    # overnight_trades uses open/close columns. We passed spy prices. Cost is 0.02 dollars.
    return metrics(source, cost=0.02)


def main() -> None:
    folder = Path("/tmp/rare_data/daily")
    frame = build_daily(folder)[0]
    rules = daily_rules(frame)
    kinds = {}
    for name in rules:
        if name in {"overnight_all", "overnight_contango", "overnight_tom"}:
            kinds[name] = "overnight"
        elif name in CLOSE_TO_CLOSE:
            kinds[name] = "closeclose"
        elif name in {"gap_fade", "gap_go", "nfp_gap_fade"}:
            kinds[name] = "same"
        else:
            kinds[name] = "next"
    builders = {
        "overnight": overnight_trades,
        "closeclose": closeclose_trades,
        "same": same_bar_trades,
        "next": next_open_trades,
    }
    results = []
    daily_pnl = {}
    oos_index = pd.bdate_range(OOS_START, frame.index.max())
    for name, side in rules.items():
        trades = builders[kinds[name]](frame, side)
        base = metrics(trades, COST)
        double = metrics(trades, COST * 2)
        results.append({"name": name, "kind": kinds[name], "base": base, "double": double})
        series = pd.Series(0.0, index=oos_index)
        for item in trades:
            series[pd.Timestamp(item["day"])] = series.get(pd.Timestamp(item["day"]), 0.0) + item["gross"] - COST
        daily_pnl[name] = series
        print(name, "trades", base["trades"], "win", base["win_rate"], "exp", base["expectancy"], "ci", base["expectancy_ci"], "pf", base["profit_factor"], flush=True)
    wf = walk_forward_rsi(frame)
    wf_base = metrics(wf, COST)
    wf_double = metrics(wf, COST * 2)
    results.append({"name": "rsi2_walkforward_5_or_10", "kind": "next", "base": wf_base, "double": wf_double})
    print("walkforward", wf_base["trades"], wf_base["win_rate"], wf_base["expectancy"], wf_base["expectancy_ci"], flush=True)
    series = pd.Series(0.0, index=oos_index)
    for item in wf:
        series[pd.Timestamp(item["day"])] = series.get(pd.Timestamp(item["day"]), 0.0) + item["gross"] - COST
    daily_pnl["rsi2_walkforward_5_or_10"] = series
    m5 = sorted(Path("/tmp/rare_data/m5").glob("usa500*.csv"))
    if m5:
        print("intraday", m5[0].name, flush=True)
        intra = intraday(m5[0])
        for name, trades in intra.items():
            base = metrics(trades, COST)
            double = metrics(trades, COST * 2)
            results.append({"name": name, "kind": "intraday", "base": base, "double": double})
            series = pd.Series(0.0, index=oos_index)
            for item in trades:
                stamp = pd.Timestamp(item["day"])
                if stamp in series.index:
                    series[stamp] += item["gross"] - COST
            daily_pnl[name] = series
            print(name, base["trades"], base["win_rate"], base["expectancy"], base["expectancy_ci"], base["profit_factor"], flush=True)
    names = list(daily_pnl)
    matrix = np.column_stack([daily_pnl[name].to_numpy(float) for name in names])
    # Rank by the lower expectancy bound. This ranking is not allowed to add rules.
    ranked = sorted(results, key=lambda row: ((row["base"]["expectancy_ci"] or [-999, -999])[0], row["base"]["expectancy"] or -999), reverse=True)
    best_name = ranked[0]["name"]
    col = names.index(best_name)
    reality = whites_reality_check(matrix, float(matrix[:, col].mean()))
    dsr = deflated_sharpe_of(matrix[:, col], deflated_sharpe(matrix, len(names))["sr_star"])
    decision = passes(ranked[0]["base"], ranked[0]["double"], reality, dsr)
    # Also test every rule against the same bars so the report can say none passed,
    # without promoting a later one after seeing the test. Promotion is only the top-ranked.
    others = []
    for row in ranked:
        col_i = names.index(row["name"])
        real_i = whites_reality_check(matrix, float(matrix[:, col_i].mean()))
        dsr_i = deflated_sharpe_of(matrix[:, col_i], deflated_sharpe(matrix, len(names))["sr_star"])
        others.append({"name": row["name"], "decision": passes(row["base"], row["double"], real_i, dsr_i)})
    payload = {
        "configs": len(names),
        "config_names": names,
        "oos_start": OOS_START.isoformat(),
        "price": "Yahoo ^GSPC daily for daily rules. Dukascopy USA500 5-minute bid from 2011-09-18 for the two intraday rules. VIX9D, VVIX and SKEW were downloaded and not used, so they do not enter the count.",
        "cost_round_trip_points": COST,
        "ranked": [{
            "name": row["name"], "kind": row["kind"], **{k: v for k, v in row["base"].items() if k != "years"},
            "years": row["base"]["years"], "double_expectancy": row["double"]["expectancy"],
            "double_expectancy_ci": row["double"]["expectancy_ci"], "double_profit_factor": row["double"]["profit_factor"],
        } for row in ranked],
        "reality_check_top": reality,
        "deflated_sharpe_top": {k: v for k, v in dsr.items()},
        "promotion_top": {"name": best_name, **decision},
        "promotion_each": others,
        "live_default": "rare" if decision["promote"] else "legacy",
    }
    out = Path("artifacts/rare_setups")
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TOP", best_name, decision)


if __name__ == "__main__":
    main()
