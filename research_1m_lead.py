"""1-minute context study for an early SPY/SPX explosion alert.

The explosion is unchanged: within 30 minutes one side reaches
max(0.30% of the anchor close, 3 x the prior 14-bar *five-minute* ATR)
and the other side does not hit that distance first. Onset is the first
one-minute bar that covers 25% of the target.

This pass does not retest 5-minute compression or volume-inside-a-tight-range.
Context features are fixed before the isolated test is read. Validation
selects one candidate. Promotion requires the latency-and-cost early-recall
interval on the isolated test to sit entirely above the legacy interval.

IBKR historical bars are not available in this environment. Prices are Yahoo
chart 1-minute bars. A single live snapshot showed VIX about 15 minutes
behind SPY, so VIX, VIX1D and the NYSE composite are lagged 15 minutes.
SPY itself is charged 60 seconds after the one-minute close plus one cent
per share (half the typical spread plus a per-share commission).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
HORIZON_MINUTES = 30
TARGET_PCT = 0.003
TARGET_ATR = 3.0
ONSET_FRACTION = 0.25
LATENCY = pd.Timedelta(seconds=60)
SHARE_COST = 0.01  # half-spread 0.005 plus 0.005 commission, one side, SPY
MATCH_LOOKBACK = pd.Timedelta(minutes=30)
# Official calendars locked before scoring: FOMC second day, NFP, CPI.
# CPI falls on the in-progress session of the fetch day and is dropped with it.
MACRO = (
    ("FOMC", "2026-10-28", 14, 0),
    ("NFP", "2026-11-06", 8, 30),
    ("CPI", "2026-11-10", 8, 30),
)
# Flipped only if the predeclared promotion rule passes on the single test read.
CONTEXT_PROMOTED = False
CANDIDATES = (
    "open_drive",
    "vwap_start",
    "vix_lag15",
    "vix1d_lag15",
    "macro_release",
    "nya_lag15",
)


def wilson(successes: int, trials: int, z: float = 1.96) -> list | None:
    if trials <= 0:
        return None
    phat = successes / trials
    den = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / den
    margin = z * ((phat * (1 - phat) / trials + z * z / (4 * trials * trials)) ** 0.5) / den
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def ny_date(ts: pd.Timestamp):
    return ts.tz_convert(NY).date()


def in_rth(ts: pd.Timestamp) -> bool:
    local = ts.tz_convert(NY)
    minutes = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def load_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col in frame:
            frame[col] = frame[col].astype(float)
    return frame


def drop_partial_last_session(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    last = frame.index[-1].tz_convert(NY)
    if last.hour * 60 + last.minute >= 15 * 60 + 55:
        return frame
    last_day = last.date()
    dates = frame.index.tz_convert(NY).date
    day = frame.loc[dates == last_day]
    rth = day.loc[[in_rth(ts) for ts in day.index]]
    if len(rth) and rth.index[-1].tz_convert(NY).hour >= 14:
        return frame.loc[dates < last_day]
    return frame


def rth_sessions(frame: pd.DataFrame, minimum: int = 300) -> list:
    dates = frame.index.tz_convert(NY).date
    counts: dict = {}
    for ts, day in zip(frame.index, dates):
        if in_rth(ts):
            counts[day] = counts.get(day, 0) + 1
    return [day for day, count in sorted(counts.items()) if count >= minimum]


def split_sessions(sessions: list) -> dict[str, list]:
    """Last four sessions are the isolated test, the four before them validation."""
    if len(sessions) < 12:
        raise ValueError(f"need at least 12 complete sessions, found {len(sessions)}")
    return {
        "train": sessions[:-8],
        "validation": sessions[-8:-4],
        "test": sessions[-4:],
    }


def five_minute(frame: pd.DataFrame) -> pd.DataFrame:
    grouped = frame.groupby(frame.index.floor("5min")).agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
        Close=("Close", "last"), Volume=("Volume", "sum"), n=("Close", "count"),
    )
    return grouped.loc[grouped["n"] == 5].drop(columns="n")


def five_minute_atr(frame: pd.DataFrame) -> pd.Series:
    bars = five_minute(frame)
    previous = bars["Close"].shift()
    tr = pd.concat([
        bars["High"] - bars["Low"],
        (bars["High"] - previous).abs(),
        (bars["Low"] - previous).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean().shift(1)
    atr.index = bars.index + pd.Timedelta(minutes=5)
    return atr.dropna()


def legacy_signals(
    frame: pd.DataFrame,
    lookback: int = 30,
    rvol_min: float = 2.0,
    momentum_pct: float = 0.35,
    min_distance_atr: float = 0.1,
) -> list[dict]:
    """5-minute confirmation built only from completed one-minute groups.

    Defaults are the live rule: 30-bar range, RVOL >= 2, five-bar move >= 0.35%,
    distance >= 0.1 ATR. `momentum_pct` is in percent, matching EXPLOSION_LEGACY_MOMENTUM_PCT.
    """
    bars = five_minute(frame)
    need = max(lookback, 14, 5) + 2
    if len(bars) < need:
        return []
    previous = bars["Close"].shift()
    tr = pd.concat([
        bars["High"] - bars["Low"],
        (bars["High"] - previous).abs(),
        (bars["Low"] - previous).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=14).mean().shift(1)
    prior_high = bars["High"].rolling(lookback, min_periods=lookback).max().shift(1)
    prior_low = bars["Low"].rolling(lookback, min_periods=lookback).min().shift(1)
    vol_mean = bars["Volume"].rolling(lookback, min_periods=lookback).mean().shift(1)
    momentum = bars["Close"] / bars["Close"].shift(5) - 1
    momentum_floor = momentum_pct / 100.0
    out = []
    for ts, row in bars.iterrows():
        if not in_rth(ts):
            continue
        a = atr.get(ts, np.nan)
        ph, pl, base, mom = prior_high.get(ts, np.nan), prior_low.get(ts, np.nan), vol_mean.get(ts, np.nan), momentum.get(ts, np.nan)
        if not all(np.isfinite(x) for x in (a, ph, pl, base, mom)) or a <= 0 or base <= 0 or row["Volume"] <= 0:
            continue
        rvol = float(row["Volume"] / base)
        close = float(row["Close"])
        if rvol < rvol_min or abs(mom) < momentum_floor:
            continue
        if close > ph and mom > 0 and (close - ph) >= min_distance_atr * a:
            direction = "BULLISH"
        elif close < pl and mom < 0 and (pl - close) >= min_distance_atr * a:
            direction = "BEARISH"
        else:
            continue
        end = ts + pd.Timedelta(minutes=5)
        out.append(_signal("legacy", ts, end, direction, close, float(a), ny_date(ts)))
    return out


def _signal(name: str, start: pd.Timestamp, end: pd.Timestamp, direction: str, close: float, atr: float, day) -> dict:
    cost = SHARE_COST if direction == "BULLISH" else -SHARE_COST
    return {
        "name": name,
        "day": day,
        "bar_start": start,
        "bar_end": end,
        "decision_gross": end,
        "decision_net": end + LATENCY,
        "direction": direction,
        "close": close,
        "entry_gross": close,
        "entry_net": close + cost,
        "atr": atr,
    }


def _asof_fresh(series: pd.Series, moment: pd.Timestamp, tolerance: pd.Timedelta) -> float:
    if series.empty:
        return np.nan
    pos = series.index.searchsorted(moment, side="right") - 1
    if pos < 0:
        return np.nan
    stamp = series.index[pos]
    if moment - stamp > tolerance:
        return np.nan
    value = float(series.iloc[pos])
    return value if np.isfinite(value) else np.nan


def _cooldown(rows: list[dict], minutes: int) -> list[dict]:
    kept = []
    last: dict[str, pd.Timestamp] = {}
    for row in rows:
        prev = last.get(row["direction"])
        if prev is not None and row["bar_end"] - prev < pd.Timedelta(minutes=minutes):
            continue
        kept.append(row)
        last[row["direction"]] = row["bar_end"]
    return kept


def _atr_at(atr: pd.Series, moment: pd.Timestamp) -> float:
    # Last completed five-minute ATR remains usable across the overnight gap.
    return _asof_fresh(atr, moment, pd.Timedelta(days=5))


def context_signals(spy: pd.DataFrame, aux: dict[str, pd.DataFrame], atr: pd.Series) -> dict[str, list[dict]]:
    """Fixed context rules. Auxiliary prices are read only through their own timestamps."""
    local = spy.index.tz_convert(NY)
    dates = np.array(local.date)
    minutes = np.array(local.hour * 60 + local.minute)
    close = spy["Close"].to_numpy(dtype=float)
    open_ = spy["Open"].to_numpy(dtype=float)
    high = spy["High"].to_numpy(dtype=float)
    low = spy["Low"].to_numpy(dtype=float)
    volume = spy["Volume"].to_numpy(dtype=float)
    index = spy.index
    rth = np.array([in_rth(ts) for ts in index])
    vix = _end_series(aux.get("^VIX"))
    vix1d = _end_series(aux.get("^VIX1D"))
    nya = _end_series(aux.get("^NYA"))

    buckets: dict[str, list[dict]] = {name: [] for name in CANDIDATES}
    seen_open: set[tuple] = set()
    day_open: dict = {}
    cum_pv = 0.0
    cum_v = 0.0
    current_day = None
    for i, ts in enumerate(index):
        day = dates[i]
        if day != current_day:
            current_day = day
            cum_pv = 0.0
            cum_v = 0.0
            day_open.pop(day, None)
        if rth[i] and day not in day_open:
            day_open[day] = float(open_[i])
        typical = (high[i] + low[i] + close[i]) / 3.0
        if np.isfinite(typical) and volume[i] > 0 and rth[i]:
            cum_pv += typical * volume[i]
            cum_v += volume[i]
        if not rth[i]:
            continue
        session_index = int(minutes[i] - (9 * 60 + 30))
        a = _atr_at(atr, ts)
        end = ts + pd.Timedelta(minutes=1)
        # Opening drive at the 5th, 10th and 15th completed minute.
        if session_index in (4, 9, 14) and day in day_open and i > 0 and close[i - 1] > 0:
            ret = close[i] / day_open[day] - 1.0
            last = close[i] / close[i - 1] - 1.0
            direction = None
            if 0.0006 <= ret <= 0.0014 and last >= 0.0002:
                direction = "BULLISH"
            elif -0.0014 <= ret <= -0.0006 and last <= -0.0002:
                direction = "BEARISH"
            if direction and (day, direction) not in seen_open and np.isfinite(a):
                seen_open.add((day, direction))
                buckets["open_drive"].append(_signal("open_drive", ts, end, direction, float(close[i]), a, day))
        # VWAP deviation starting to widen, still under 0.12%.
        if session_index >= 10 and cum_v > 0 and i >= 3 and dates[i - 3] == day:
            vwap_now = cum_pv / cum_v
            dev = (close[i] - vwap_now) / close[i]
            back_pv, back_v = cum_pv, cum_v
            for k in range(i, i - 3, -1):
                if volume[k] > 0:
                    back_pv -= ((high[k] + low[k] + close[k]) / 3.0) * volume[k]
                    back_v -= volume[k]
            if back_v > 0 and close[i - 3] > 0 and np.isfinite(a):
                dev_then = (close[i - 3] - back_pv / back_v) / close[i - 3]
                direction = None
                if dev >= 0.0004 and dev >= dev_then + 0.0003 and dev <= 0.0012:
                    direction = "BULLISH"
                elif dev <= -0.0004 and dev <= dev_then - 0.0003 and dev >= -0.0012:
                    direction = "BEARISH"
                if direction:
                    buckets["vwap_start"].append(_signal("vwap_start", ts, end, direction, float(close[i]), a, day))
        if np.isfinite(a):
            _vol_signal(buckets, "vix_lag15", vix, None, ts, end, close, index, i, a, day, level=0.15, scale="points")
            _vol_signal(buckets, "vix1d_lag15", vix1d, vix, ts, end, close, index, i, a, day, level=0.20, scale="spread")
            _nya_signal(buckets, nya, ts, end, close, index, i, a, day)
        _macro_signal(buckets, spy, ts, end, close, i, a, day)
    buckets["vwap_start"] = _cooldown(buckets["vwap_start"], 10)
    buckets["vix_lag15"] = _cooldown(buckets["vix_lag15"], 15)
    buckets["vix1d_lag15"] = _cooldown(buckets["vix1d_lag15"], 15)
    buckets["nya_lag15"] = _cooldown(buckets["nya_lag15"], 15)
    return buckets


def _end_series(frame: pd.DataFrame | None) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    series = frame["Close"].copy()
    series.index = frame.index + pd.Timedelta(minutes=1)
    return series.sort_index()


def _spy_return(close: np.ndarray, index: pd.DatetimeIndex, i: int, minutes: int) -> float:
    target = index[i] - pd.Timedelta(minutes=minutes)
    pos = index.searchsorted(target, side="right") - 1
    if pos < 0 or close[pos] <= 0:
        return np.nan
    if index[i] - index[pos] > pd.Timedelta(minutes=minutes + 2):
        return np.nan
    return float(close[i] / close[pos] - 1.0)


def _lagged_delta(series: pd.Series, end: pd.Timestamp, span: int = 5) -> float:
    """Change ending 15 minutes before `end`, so a delayed print cannot be used early."""
    latest = end - pd.Timedelta(minutes=15)
    earlier = latest - pd.Timedelta(minutes=span)
    v1 = _asof_fresh(series, latest, pd.Timedelta(minutes=2))
    v0 = _asof_fresh(series, earlier, pd.Timedelta(minutes=2))
    if not np.isfinite(v1) or not np.isfinite(v0):
        return np.nan
    return v1 - v0


def _vol_signal(buckets, name, primary, secondary, ts, end, close, index, i, atr, day, level, scale):
    if primary.empty:
        return
    if scale == "points":
        change = _lagged_delta(primary, end)
    else:
        if secondary is None or secondary.empty:
            return
        # Both legs must exist at the same lagged moments.
        latest = end - pd.Timedelta(minutes=15)
        earlier = latest - pd.Timedelta(minutes=5)
        now_p, then_p = _asof_fresh(primary, latest, pd.Timedelta(minutes=2)), _asof_fresh(primary, earlier, pd.Timedelta(minutes=2))
        now_s, then_s = _asof_fresh(secondary, latest, pd.Timedelta(minutes=2)), _asof_fresh(secondary, earlier, pd.Timedelta(minutes=2))
        if not all(np.isfinite(x) for x in (now_p, then_p, now_s, then_s)):
            return
        change = (now_p - now_s) - (then_p - then_s)
    if not np.isfinite(change):
        return
    recent = _spy_return(close, index, i, 10)
    if not np.isfinite(recent):
        return
    direction = None
    if change >= level and recent > -0.0010:
        direction = "BEARISH"
    elif change <= -level and recent < 0.0010:
        direction = "BULLISH"
    if direction:
        buckets[name].append(_signal(name, ts, end, direction, float(close[i]), atr, day))


def _nya_signal(buckets, nya, ts, end, close, index, i, atr, day):
    if nya.empty:
        return
    latest = end - pd.Timedelta(minutes=15)
    earlier = latest - pd.Timedelta(minutes=5)
    v1 = _asof_fresh(nya, latest, pd.Timedelta(minutes=2))
    v0 = _asof_fresh(nya, earlier, pd.Timedelta(minutes=2))
    if not np.isfinite(v1) or not np.isfinite(v0) or v0 <= 0:
        return
    change = v1 / v0 - 1.0
    recent = _spy_return(close, index, i, 10)
    if not np.isfinite(recent):
        return
    direction = None
    if change >= 0.0008 and 0 <= recent <= 0.0010:
        direction = "BULLISH"
    elif change <= -0.0008 and -0.0010 <= recent <= 0:
        direction = "BEARISH"
    if direction:
        buckets["nya_lag15"].append(_signal("nya_lag15", ts, end, direction, float(close[i]), atr, day))


def _macro_signal(buckets, spy: pd.DataFrame, ts, end, close, i, atr, day):
    if not np.isfinite(atr):
        return
    local = ts.tz_convert(NY)
    for kind, date, hour, minute in MACRO:
        if str(day) != date:
            continue
        if hour == 8:
            # Premarket release: alert at 09:35 only if the open is still a small continuation.
            if not (local.hour == 9 and local.minute == 34):
                continue
            pre = _window_return(spy, day, 8, 30, 9, 29)
            rth_open = _price_at(spy, day, 9, 30, "Open")
            if not np.isfinite(pre) or not np.isfinite(rth_open) or rth_open <= 0:
                continue
            rth_ret = close[i] / rth_open - 1.0
            direction = None
            if pre >= 0.0008 and 0 <= rth_ret <= 0.0012:
                direction = "BULLISH"
            elif pre <= -0.0008 and -0.0012 <= rth_ret <= 0:
                direction = "BEARISH"
        else:
            if not (local.hour == hour and local.minute == minute + 4):
                continue
            release = _price_at(spy, day, hour, minute, "Open")
            move = close[i] / release - 1.0 if np.isfinite(release) and release > 0 else np.nan
            direction = None
            if np.isfinite(move) and 0.0004 <= move <= 0.0012:
                direction = "BULLISH"
            elif np.isfinite(move) and -0.0012 <= move <= -0.0004:
                direction = "BEARISH"
        if direction:
            buckets["macro_release"].append(_signal("macro_release", ts, end, direction, float(close[i]), atr, day))


def _price_at(frame: pd.DataFrame, day, hour: int, minute: int, field: str) -> float:
    local = frame.index.tz_convert(NY)
    mask = (local.date == day) & (local.hour == hour) & (local.minute == minute)
    if not mask.any():
        return np.nan
    return float(frame.loc[mask, field].iloc[0])


def _window_return(frame: pd.DataFrame, day, h0, m0, h1, m1) -> float:
    start = _price_at(frame, day, h0, m0, "Open")
    end = _price_at(frame, day, h1, m1, "Close")
    if not np.isfinite(start) or not np.isfinite(end) or start <= 0:
        return np.nan
    return end / start - 1.0


def build_events(frame: pd.DataFrame, atr: pd.Series) -> list[dict]:
    index = frame.index
    high = frame["High"].to_numpy(dtype=float)
    low = frame["Low"].to_numpy(dtype=float)
    close = frame["Close"].to_numpy(dtype=float)
    rth = np.array([in_rth(ts) for ts in index])
    events = []
    i = 1
    n = len(frame)
    while i < n - 1:
        if not rth[i] or index[i] - index[i - 1] > pd.Timedelta(minutes=2):
            i += 1
            continue
        a = _atr_at(atr, index[i])
        if not np.isfinite(a) or a <= 0 or close[i - 1] <= 0:
            i += 1
            continue
        p0 = float(close[i - 1])
        target = max(TARGET_PCT * p0, TARGET_ATR * a)
        end = i
        limit = min(n, i + HORIZON_MINUTES)
        while end < limit and ny_date(index[end]) == ny_date(index[i]) and (end == i or index[end] - index[end - 1] <= pd.Timedelta(minutes=2)):
            end += 1
        if end <= i:
            i += 1
            continue
        first_up = first_down = None
        for j in range(i, end):
            if first_up is None and high[j] - p0 >= target:
                first_up = j
            if first_down is None and p0 - low[j] >= target:
                first_down = j
        if first_up is None and first_down is None:
            i += 1
            continue
        if first_up is not None and first_down is not None and first_up == first_down:
            i += 1
            continue
        if first_up is not None and (first_down is None or first_up < first_down):
            direction, touch = "BULLISH", first_up
        else:
            direction, touch = "BEARISH", first_down
        onset = None
        for j in range(i, touch + 1):
            excursion = (high[j] - p0) if direction == "BULLISH" else (p0 - low[j])
            if excursion >= ONSET_FRACTION * target:
                onset = j
                break
        if onset != i:
            i += 1
            continue
        extreme = float(high[onset:touch + 1].max()) if direction == "BULLISH" else float(low[onset:touch + 1].min())
        events.append({
            "onset": index[onset],
            "touch": index[touch],
            "direction": direction,
            "p0": p0,
            "extreme": extreme,
            "target": target,
            "atr": a,
            "day": ny_date(index[onset]),
        })
        i = touch + 1
    return events


def _decision(signal: dict, mode: str) -> pd.Timestamp:
    return signal["decision_net"] if mode == "net" else signal["decision_gross"]


def _entry(signal: dict, mode: str) -> float:
    return signal["entry_net"] if mode == "net" else signal["entry_gross"]


def evaluate(signals: list[dict], events: list[dict], frame: pd.DataFrame, sessions: list, mode: str = "net") -> dict:
    chosen = set(sessions)
    kept_events = [event for event in events if event["day"] in chosen]
    kept = [signal for signal in signals if signal["day"] in chosen]
    index = frame.index
    high = frame["High"].to_numpy(dtype=float)
    low = frame["Low"].to_numpy(dtype=float)
    early = 0
    matched = 0
    leads = []
    qualities = []
    lead_sessions = []
    for event in kept_events:
        window = []
        for signal in kept:
            if signal["direction"] != event["direction"]:
                continue
            decision = _decision(signal, mode)
            if decision > event["touch"]:
                continue
            if event["onset"] - decision > MATCH_LOOKBACK:
                continue
            window.append(signal)
        if not window:
            continue
        signal = min(window, key=lambda row: _decision(row, mode))
        decision = _decision(signal, mode)
        lead = (event["onset"] - decision).total_seconds() / 60.0
        entry = _entry(signal, mode)
        if event["direction"] == "BULLISH":
            total = event["extreme"] - event["p0"]
            remaining = event["extreme"] - entry
        else:
            total = event["p0"] - event["extreme"]
            remaining = entry - event["extreme"]
        matched += 1
        leads.append(lead)
        lead_sessions.append(event["day"])
        qualities.append(remaining / total if total > 0 else 0.0)
        if lead > 0:
            early += 1
    hits = 0
    scored = 0
    false_by_session = {day: 0 for day in sessions}
    scored_by_session = {day: 0 for day in sessions}
    for signal in kept:
        decision = _decision(signal, mode)
        start = index.searchsorted(decision, side="left")
        stop_time = decision + pd.Timedelta(minutes=HORIZON_MINUTES)
        stop = index.searchsorted(stop_time, side="left")
        if stop - start < 15:
            continue
        segment_h = high[start:stop]
        segment_l = low[start:stop]
        if len(segment_h) == 0 or not np.isfinite(signal["atr"]) or signal["atr"] <= 0:
            continue
        target = max(TARGET_PCT * signal["close"], TARGET_ATR * signal["atr"])
        entry = _entry(signal, mode)
        favorable = (float(segment_h.max()) - entry) if signal["direction"] == "BULLISH" else (entry - float(segment_l.min()))
        scored += 1
        scored_by_session[signal["day"]] += 1
        if favorable >= target:
            hits += 1
        else:
            false_by_session[signal["day"]] += 1
    sessions_n = len(sessions)
    false_alarms = scored - hits
    fa_values = [false_by_session[day] for day in sessions]
    return {
        "mode": mode,
        "sessions": sessions_n,
        "start": sessions[0].isoformat() if sessions else None,
        "end": sessions[-1].isoformat() if sessions else None,
        "events": len(kept_events),
        "signals": len(kept),
        "matched_events": matched,
        "recall_before_onset": round(early / len(kept_events), 4) if kept_events else None,
        "recall_before_onset_wilson95": wilson(early, len(kept_events)),
        "early_matches": early,
        "median_lead_min": None if not leads else round(float(np.median(leads)), 2),
        "median_lead_bootstrap95": _bootstrap_median(leads, lead_sessions, sessions),
        "median_entry_quality": None if not qualities else round(float(np.median(qualities)), 4),
        "forward_hits": hits,
        "forward_scored": scored,
        "forward_hit_rate": round(hits / scored, 4) if scored else None,
        "forward_hit_wilson95": wilson(hits, scored),
        "false_alarms": false_alarms,
        "false_alarms_per_session": round(false_alarms / sessions_n, 4) if sessions_n else None,
        "false_alarms_per_session_bootstrap95": _bootstrap_mean(fa_values),
    }


def _bootstrap_mean(values: list[float], draws: int = 500, seed: int = 16) -> list | None:
    if not values:
        return None
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    samples = [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(draws)]
    return [round(float(np.quantile(samples, 0.025)), 4), round(float(np.quantile(samples, 0.975)), 4)]


def _bootstrap_median(leads: list[float], owners: list, sessions: list, draws: int = 500, seed: int = 16) -> list | None:
    if len(leads) < 2:
        return None
    by_day: dict = {}
    for lead, day in zip(leads, owners):
        by_day.setdefault(day, []).append(lead)
    days = [day for day in sessions if day in by_day]
    if len(days) < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(draws):
        picked = rng.choice(np.array(days, dtype=object), size=len(days), replace=True)
        pooled = [value for day in picked for value in by_day[day]]
        samples.append(float(np.median(pooled)))
    return [round(float(np.quantile(samples, 0.025)), 2), round(float(np.quantile(samples, 0.975)), 2)]


def select_candidate(validation: dict[str, dict]) -> dict:
    ranked = []
    for name, row in validation.items():
        if name == "legacy" or not row["signals"]:
            continue
        ranked.append((
            row["recall_before_onset"] or -1,
            row["median_lead_min"] if row["median_lead_min"] is not None else -999,
            row["median_entry_quality"] if row["median_entry_quality"] is not None else -999,
            -(row["false_alarms_per_session"] or 0),
            name,
        ))
    if not ranked:
        return {"selected": None, "reason": "no context candidate produced a validation signal"}
    ranked.sort(reverse=True)
    return {"selected": ranked[0][-1], "reason": "highest validation early-recall, then lead, entry quality, and fewer false alarms"}


def promote(candidate: dict | None, legacy: dict) -> dict:
    """Isolated-test rule. Intervals must not overlap, and costs are already in the rows."""
    if candidate is None:
        return {"promote": False, "reason": "no selected candidate"}
    cand_ci = candidate.get("recall_before_onset_wilson95")
    leg_ci = legacy.get("recall_before_onset_wilson95")
    if not cand_ci or not leg_ci:
        return {"promote": False, "reason": "missing recall interval"}
    separated = cand_ci[0] > leg_ci[1]
    quality_ok = (
        candidate.get("median_entry_quality") is not None
        and (legacy.get("median_entry_quality") is None or candidate["median_entry_quality"] >= legacy["median_entry_quality"])
    )
    fa_ok = (
        candidate.get("false_alarms_per_session") is not None
        and legacy.get("false_alarms_per_session") is not None
        and candidate["false_alarms_per_session"] <= legacy["false_alarms_per_session"] + 0.25
    )
    hit_ci = candidate.get("forward_hit_wilson95")
    leg_hit = legacy.get("forward_hit_wilson95")
    hit_not_worse = bool(hit_ci and leg_hit and hit_ci[1] >= leg_hit[0])
    ok = separated and quality_ok and fa_ok and hit_not_worse
    return {
        "promote": ok,
        "recall_intervals_separated": separated,
        "entry_quality_not_worse": quality_ok,
        "false_alarms_not_materially_worse": fa_ok,
        "forward_hit_not_entirely_worse": hit_not_worse,
        "reason": "early-recall interval entirely above legacy, with entry quality and false alarms held" if ok else "promotion gates failed",
    }


def run_study(frames: dict[str, pd.DataFrame], spent_through: str | None = None) -> dict:
    spy = drop_partial_last_session(frames["SPY"])
    sessions = rth_sessions(spy)
    if spent_through:
        cutoff = datetime.fromisoformat(spent_through).date()
        sessions = [day for day in sessions if day > cutoff]
        if len(sessions) < 12:
            return {
                "status": "WAITING_FOR_NEW_SESSIONS",
                "spent_through": spent_through,
                "new_sessions": len(sessions),
                "needed": 12,
                "verdict_ar": (
                    f"NOT READY. بعد {spent_through} توجد {len(sessions)} جلسات جديدة فقط. "
                    "يلزم 12 جلسة على الأقل قبل تقسيم تدريب/تحقق/اختبار جديد. لم يُحسب اختبار."
                ),
            }
    parts = split_sessions(sessions)
    atr = five_minute_atr(spy)
    events = build_events(spy, atr)
    legacy = legacy_signals(spy)
    context = context_signals(spy, frames, atr)
    validation = {"legacy": evaluate(legacy, events, spy, parts["validation"], "net")}
    train = {"legacy": evaluate(legacy, events, spy, parts["train"], "net")}
    for name, signals in context.items():
        validation[name] = evaluate(signals, events, spy, parts["validation"], "net")
        train[name] = evaluate(signals, events, spy, parts["train"], "net")
    choice = select_candidate(validation)
    selected = choice["selected"]
    test = {"legacy": _pair(legacy, events, spy, parts["test"])}
    if selected:
        test[selected] = _pair(context[selected], events, spy, parts["test"])
    decision = promote(test.get(selected, {}).get("net") if selected else None, test["legacy"]["net"])
    fresh = [day for day in sessions if day > datetime(2026, 11, 4).date()]
    transfer = _index_transfer(frames.get("^GSPC"), frames, parts["test"], selected)
    return {
        "sessions": {name: [day.isoformat() for day in days] for name, days in parts.items()},
        "session_count": len(sessions),
        "event_definition": "30 one-minute bars, max(0.30%, 3 x prior 14 five-minute ATR), other side must not hit first",
        "costs": {
            "spy_latency_seconds": 60,
            "vix_lag_minutes": 15,
            "share_cost_usd": SHARE_COST,
            "share_cost_note": "0.005 half of a one-cent spread plus 0.005 per-share commission, charged on the entry",
        },
        "train_net": train,
        "validation_net": validation,
        "selection": choice,
        "test": test,
        "promotion": decision,
        "spx_transfer": transfer,
        "unconsumed_after_2026_11_04": {
            "legacy": _pair(legacy, events, spy, fresh),
            "selected": _pair(context[selected], events, spy, fresh) if selected else None,
            "note": "Same sessions as the isolated test if the split already ends there. Not used to select.",
        },
    }


def _index_transfer(gspc: pd.DataFrame | None, frames: dict, test_days: list, selected: str | None) -> dict:
    """Same frozen rule on ^GSPC. Not used for selection or promotion."""
    if gspc is None or gspc.empty or not selected:
        return {"note": "no index bars or no selected rule"}
    gspc = drop_partial_last_session(gspc)
    days = [day for day in test_days if day in set(rth_sessions(gspc, minimum=100))]
    if not days:
        return {"note": "index has none of the SPY test sessions"}
    atr = five_minute_atr(gspc)
    events = build_events(gspc, atr)
    context = context_signals(gspc, frames, atr)
    return {
        "note": "Descriptive transfer. A one-cent share cost is negligible on the index and is not an option spread.",
        "sessions": [day.isoformat() for day in days],
        "legacy": _pair(legacy_signals(gspc), events, gspc, days),
        "selected": _pair(context[selected], events, gspc, days),
    }


def _pair(signals, events, frame, sessions) -> dict:
    return {
        "gross": evaluate(signals, events, frame, sessions, "gross"),
        "net": evaluate(signals, events, frame, sessions, "net"),
    }


def arabic_verdict(report: dict) -> str:
    decision = report["promotion"]
    selected = report["selection"]["selected"]
    legacy = report["test"]["legacy"]["net"]
    if not selected:
        return (
            "NOT READY. لا توجد إشارة سياق أنتجت صفقة على التحقق، "
            "لذلك لم يُعتمد أي كاشف مبكر ولم يُغيَّر التنبيه الحي."
        )
    cand = report["test"][selected]["net"]
    verdict = "READY" if decision["promote"] else "NOT READY"
    return (
        f"{verdict}. المرشح المختار على التحقق هو {selected}. "
        f"على الاختبار المعزول ({cand['start']} إلى {cand['end']}، {cand['sessions']} جلسات، {cand['events']} انفجارات) "
        f"وبعد 60 ثانية تأخير وسنت واحد تكلفة: استدعاء قبل بداية الحركة {cand['recall_before_onset']} "
        f"(فترة 95% {cand['recall_before_onset_wilson95']}) مقابل {legacy['recall_before_onset']} "
        f"({legacy['recall_before_onset_wilson95']}) للقاعدة القديمة. "
        f"وسيط السبق {cand['median_lead_min']} دقيقة مقابل {legacy['median_lead_min']}. "
        f"وسيط جودة الدخول {cand['median_entry_quality']} مقابل {legacy['median_entry_quality']}. "
        f"إصابة 30 دقيقة {cand['forward_hit_rate']} مقابل {legacy['forward_hit_rate']}. "
        f"إنذارات كاذبة لكل جلسة {cand['false_alarms_per_session']} مقابل {legacy['false_alarms_per_session']}. "
        f"{decision['reason']}. التنبيه الحي لم يتغير."
        if not decision["promote"] else
        f"{verdict}. المرشح {selected} تجاوز القاعدة القديمة على الاختبار المعزول بفاصل ثقة غير متداخل "
        f"لاستدعاء ما قبل البداية ({cand['recall_before_onset']} مقابل {legacy['recall_before_onset']})."
    )


def context_mode_status() -> str:
    if CONTEXT_PROMOTED:
        return "CONTEXT promoted: live sending is enabled only by the isolated-test rule."
    return (
        "NOT READY: وضع context تجريبي ولا يرسل تنبيهات. "
        "شموع دقيقة مع VIX/VIX1D/افتتاح/VWAP لم تتفوق على التأكيد القديم خارج فترة الثقة."
    )


def fetch_symbol(symbol: str) -> tuple[pd.DataFrame, list[dict]]:
    frames = []
    notes = []
    end = int(datetime.now(timezone.utc).timestamp())
    for _ in range(6):
        start = end - 8 * 86400
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
            f"?interval=1m&period1={start}&period2={end}&includePrePost=true"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
        requested = datetime.now(timezone.utc)
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                body = response.read()
                status = response.status
        except Exception as exc:
            notes.append({"symbol": symbol, "period1": start, "error": type(exc).__name__, "detail": str(exc)[:180]})
            break
        received = datetime.now(timezone.utc)
        document = json.loads(body)
        result = (document.get("chart", {}).get("result") or [None])[0]
        if not result or not result.get("timestamp"):
            notes.append({"symbol": symbol, "period1": start, "error": "empty", "status": status})
            break
        quote = result["indicators"]["quote"][0]
        frame = pd.DataFrame(
            {"Open": quote["open"], "High": quote["high"], "Low": quote["low"], "Close": quote["close"], "Volume": quote["volume"]},
            index=pd.to_datetime(result["timestamp"], unit="s", utc=True),
        ).dropna().astype(float)
        frames.append(frame)
        last_ts = frame.index[-1].to_pydatetime()
        notes.append({
            "symbol": symbol,
            "status": status,
            "requested_at": requested.isoformat(),
            "received_at": received.isoformat(),
            "rows": int(len(frame)),
            "first": frame.index[0].isoformat(),
            "last": frame.index[-1].isoformat(),
            "last_bar_age_seconds": round((received - last_ts).total_seconds(), 3),
        })
        end = start
        time.sleep(0.35)
    if not frames:
        raise RuntimeError(f"no 1m bars for {symbol}")
    whole = pd.concat(frames).sort_index()
    whole = whole[~whole.index.duplicated(keep="last")]
    return whole, notes


def fetch_all(save_dir: Path) -> dict[str, pd.DataFrame]:
    save_dir.mkdir(parents=True, exist_ok=True)
    frames = {}
    notes = []
    for symbol in ("SPY", "^GSPC", "^VIX", "^VIX1D", "^NYA"):
        frame, meta = fetch_symbol(symbol)
        frames[symbol] = frame
        frame.to_csv(save_dir / f"{symbol.replace('^', '')}_1m.csv.gz")
        notes.extend(meta)
    (save_dir / "acquisition.json").write_text(json.dumps({
        "ibkr": "unreachable: ibapi is not installed and 127.0.0.1 ports 4001, 4002, 7496, 7497 refused",
        "unavailable": ["$TICK", "$ADD", "0DTE option flow", "gamma"],
        "chunks": notes,
    }, indent=2), encoding="utf-8")
    return frames


def load_dir(path: Path) -> dict[str, pd.DataFrame]:
    names = {"SPY": "SPY_1m.csv.gz", "^GSPC": "GSPC_1m.csv.gz", "^VIX": "VIX_1m.csv.gz", "^VIX1D": "VIX1D_1m.csv.gz", "^NYA": "NYA_1m.csv.gz"}
    return {symbol: load_frame(path / filename) for symbol, filename in names.items()}


def load_archive(path: Path) -> dict[str, pd.DataFrame]:
    """Load data/archive/<folder>/YYYY-MM-DD.csv.gz into Yahoo-symbol frames.

    Folder names omit the caret: GSPC is ^GSPC, VIX is ^VIX, VIX1D is ^VIX1D.
    """
    from archive_1m import folders_to_symbols

    frames: dict[str, list[pd.DataFrame]] = {}
    for folder, symbol in folders_to_symbols().items():
        day_dir = path / folder
        if not day_dir.is_dir():
            continue
        parts = [load_frame(day) for day in sorted(day_dir.glob("*.csv.gz"))]
        if parts:
            frames[symbol] = pd.concat(parts).sort_index()
            frames[symbol] = frames[symbol][~frames[symbol].index.duplicated(keep="last")]
    if "SPY" not in frames:
        raise FileNotFoundError(f"no SPY days under {path}")
    return frames


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="1-minute context lead study")
    parser.add_argument("--fetch", action="store_true")
    parser.add_argument("--save-dir", default="artifacts/explosion_1m")
    parser.add_argument("--archive", help="Read data/archive day files instead of a single snapshot directory")
    parser.add_argument("--spent-through", help="YYYY-MM-DD. Score only sessions after this consumed date.")
    parser.add_argument("--output", default="artifacts/explosion_1m/report.json")
    args = parser.parse_args()
    directory = Path(args.save_dir)
    if args.archive:
        frames = load_archive(Path(args.archive))
    else:
        frames = fetch_all(directory) if args.fetch or not (directory / "SPY_1m.csv.gz").exists() else load_dir(directory)
    report = run_study(frames, spent_through=args.spent_through)
    if report.get("status") == "WAITING_FOR_NEW_SESSIONS":
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(report["verdict_ar"])
        return
    report["verdict_ar"] = arabic_verdict(report)
    report["limits"] = [
        "Yahoo 1-minute history available here starts 2026-10-19, not 30 calendar days.",
        "IBKR was not reachable, so there is no broker receive-time history.",
        "One live snapshot: SPY last bar was a few seconds old; VIX, VIX1D and NYA were about 15 minutes old. Historical rows do not carry their original publication time.",
        "$TICK, $ADD and 0DTE flow/gamma were not obtainable without a paid feed.",
        "CPI on 2026-11-10 is dropped with the incomplete session. FOMC 2026-10-28 is in train. NFP 2026-11-06 falls in the isolated test and was not used to choose the candidate.",
        "Costs are a SPY share spread and commission, not an SPX option spread.",
        "The score is not a probability and no order is sent.",
    ]
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(report["verdict_ar"])
    print("promote", report["promotion"]["promote"], "selected", report["selection"]["selected"])


if __name__ == "__main__":
    main()
