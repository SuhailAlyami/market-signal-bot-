"""Research comparison of the legacy confirmation and the early range-release watch.

A signal at bar t uses bars through t only. Outcomes use later bars. No option
premium, fill, commission, or live-feed latency is simulated. The score is not a
probability.

Event (locked before the holdout is read): from an anchor close, one direction
reaches max(0.30% of price, 3 x prior ATR) within six completed 5-minute bars,
the other direction does not hit that distance first, and the onset bar itself
covers at least 25% of the distance. Lead versus onset is how much earlier the
signal bar starts. Lead versus the target touch is how much of the defined move
is still ahead. Entry quality is the fraction of that path still remaining at
the signal close.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import ibkr_market_data as market_data
from explosion_detector import (
    ExplosionConfig,
    assess_bars,
    assess_bars_legacy,
    market_session_open,
    regular_hours_start,
)

TARGET_PCT = 0.003
TARGET_ATR_MULT = 3.0
ONSET_FRACTION = 0.25
HORIZON_BARS = 6
MATCH_MINUTES = 30
FA_PER_SESSION_MAX = 2.5
SIGNALS_PER_SESSION_MAX = 3.0


def study(symbol: str, bars: pd.DataFrame, horizon: int = 6) -> dict:
    """Backtest the exact online detection logic without using future bars to decide."""
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("data must have timezone-aware bar start times")
    data = bars.sort_index()
    required = ("Open", "High", "Low", "Close", "Volume")
    if any(c not in data for c in required):
        raise ValueError("missing OHLCV columns")
    signals = []
    evaluated = 0
    for i in range(32, len(data) - horizon):
        bar_close = data.index[i] + timedelta(minutes=5)
        if not market_session_open(bar_close.to_pydatetime()):
            continue
        evaluated += 1
        prefix = data.iloc[:i + 1]
        now = bar_close.to_pydatetime() + timedelta(seconds=30)
        signal = assess_bars(symbol, prefix, now=now)
        if not signal:
            continue
        future = data.iloc[i + 1:i + 1 + horizon]
        if any((future.index[j] - data.index[i if j == 0 else i + j]) > timedelta(minutes=5)
               for j in range(len(future))):
            continue
        entry = float(data["Close"].iloc[i])
        exit_price = float(future["Close"].iloc[-1])
        signed_pct = (exit_price / entry - 1) * 100
        if signal["direction"] == "BEARISH":
            signed_pct = -signed_pct
        signals.append({
            "bar_time": signal["bar_time"],
            "direction": signal["direction"],
            "score": signal["score"],
            "rvol": round(signal["rvol"], 3),
            "entry_underlying": round(entry, 4),
            "exit_underlying": round(exit_price, 4),
            "signed_underlying_move_pct": round(signed_pct, 4),
        })
    wins = sum(x["signed_underlying_move_pct"] > 0 for x in signals)
    return {
        "symbol": symbol,
        "timeframe": "5m",
        "horizon_bars": horizon,
        "bars_evaluated": evaluated,
        "signals": len(signals),
        "positive_direction_rate": round(wins / len(signals), 4) if signals else None,
        "mean_signed_underlying_move_pct": round(
            sum(x["signed_underlying_move_pct"] for x in signals) / len(signals), 4
        ) if signals else None,
        "notes": [
            "Research metric on underlying, NOT an option contract return or tradable fill.",
            "IBKR historical bars are bounded and may be revised; no realtime execution is inferred.",
            "Exploratory in-sample metric; no out-of-sample claim.",
            "Overlapping horizons/correlated signals inflate apparent sample size.",
            "Does not include spreads, option premium decay, commissions or slippage.",
        ],
        "sample": signals[:25],
    }


def config_grid() -> list[ExplosionConfig]:
    """Predeclared candidates. Selection may use validation only."""
    grid = []
    for lookback in (6, 8, 12):
        for rvol_min in (1.6, 1.8, 2.2):
            for ext_max in (0.35, 0.45, 0.70):
                for body_min in (0.10, 0.15, 0.20):
                    grid.append(ExplosionConfig(
                        lookback=lookback,
                        rvol_min=rvol_min,
                        ext_max_atr=ext_max,
                        body_min_atr=body_min,
                    ))
    return grid


def config_name(cfg: ExplosionConfig) -> str:
    return (
        f"lb{cfg.lookback}_rv{cfg.rvol_min:.1f}_x{cfg.ext_max_atr:.2f}_b{cfg.body_min_atr:.2f}"
    )


def config_payload(cfg: ExplosionConfig) -> dict:
    raw = asdict(cfg)
    raw["max_bar_age_minutes"] = cfg.max_bar_age.total_seconds() / 60.0
    raw.pop("max_bar_age", None)
    return raw


def _as_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("data must have timezone-aware bar start times")
    data = bars.sort_index()
    required = ("Open", "High", "Low", "Close", "Volume")
    if any(col not in data for col in required):
        raise ValueError("missing OHLCV columns")
    if not data.index.is_unique:
        data = data[~data.index.duplicated(keep="last")]
    return data


def drop_partial_last_session(bars: pd.DataFrame) -> pd.DataFrame:
    """Drop an in-progress final session. A finished early close is kept."""
    data = _as_frame(bars)
    if data.empty:
        return data
    last = data.index[-1].tz_convert("America/New_York")
    if last.hour * 60 + last.minute >= 15 * 60 + 55:
        return data
    last_day = last.date()
    local_dates = data.index.tz_convert("America/New_York").date
    day = data.loc[local_dates == last_day]
    rth = day.loc[[regular_hours_start(ts) for ts in day.index]]
    if len(rth) and rth.index[-1].tz_convert("America/New_York").hour >= 14:
        return data.loc[local_dates < last_day]
    return data


def prepare_market(bars: pd.DataFrame) -> dict:
    data = _as_frame(bars)
    local = data.index.tz_convert("America/New_York")
    o = data["Open"].to_numpy(dtype=float)
    h = data["High"].to_numpy(dtype=float)
    low = data["Low"].to_numpy(dtype=float)
    c = data["Close"].to_numpy(dtype=float)
    v = data["Volume"].to_numpy(dtype=float)
    previous = np.r_[c[0], c[:-1]]
    tr = np.maximum(h - low, np.maximum(np.abs(h - previous), np.abs(low - previous)))
    rth = np.array([regular_hours_start(ts) for ts in data.index])
    day = np.array(local.date)
    return {
        "frame": data, "open": o, "high": h, "low": low, "close": c, "volume": v,
        "tr": tr, "rth": rth, "day": day, "index": data.index,
    }


def attach_outcomes(market: dict) -> dict:
    """Forward excursion from each bar close. Independent of any detector."""
    close = market["close"]
    high = market["high"]
    low = market["low"]
    index = market["index"]
    day = market["day"]
    n = len(close)
    atr = np.r_[np.nan, _rolling_mean(market["tr"], 14)[:-1]]
    hit_up = np.zeros(n, dtype=bool)
    hit_down = np.zeros(n, dtype=bool)
    horizon_ok = np.zeros(n, dtype=bool)
    for i in range(n - 1):
        if not np.isfinite(atr[i]) or atr[i] <= 0 or close[i] <= 0:
            continue
        end = i + 1
        limit = min(n, i + 1 + HORIZON_BARS)
        while end < limit and day[end] == day[i] and index[end] - index[end - 1] <= pd.Timedelta(minutes=7):
            end += 1
        if end <= i + 1:
            continue
        target = max(TARGET_PCT * close[i], TARGET_ATR_MULT * atr[i])
        horizon_ok[i] = True
        if high[i + 1:end].max() - close[i] >= target:
            hit_up[i] = True
        if close[i] - low[i + 1:end].min() >= target:
            hit_down[i] = True
    market["prior_atr14"] = atr
    market["hit_up"] = hit_up
    market["hit_down"] = hit_down
    market["horizon_ok"] = horizon_ok
    return market


def complete_sessions(market: dict, minimum_rth_bars: int = 20) -> list:
    counts: dict = {}
    for is_rth, day in zip(market["rth"], market["day"]):
        if is_rth:
            counts[day] = counts.get(day, 0) + 1
    return [day for day, count in sorted(counts.items()) if count >= minimum_rth_bars]


def _rolling_mean(values: np.ndarray, window: int) -> np.ndarray:
    out = np.full(len(values), np.nan)
    if len(values) < window:
        return out
    csum = np.cumsum(np.r_[0.0, values])
    out[window - 1:] = (csum[window:] - csum[:-window]) / window
    return out


def _rolling_max(values: np.ndarray, window: int) -> np.ndarray:
    return pd.Series(values).rolling(window, min_periods=window).max().to_numpy()


def _rolling_min(values: np.ndarray, window: int) -> np.ndarray:
    return pd.Series(values).rolling(window, min_periods=window).min().to_numpy()


def _contiguous_mask(index: pd.DatetimeIndex, lookback: int, bar_minutes: int) -> np.ndarray:
    delta = index.to_series().diff().dt.total_seconds().to_numpy()
    rolled = pd.Series(delta).rolling(lookback, min_periods=lookback).max().to_numpy()
    return np.isfinite(rolled) & (rolled <= (bar_minutes + 2) * 60)


def scan_early(market: dict, cfg: ExplosionConfig) -> list[dict]:
    """Vectorized form of raw_signal + regular-hours cooldown. Research only."""
    cfg.validate()
    n = len(market["close"])
    atr = _rolling_mean(market["tr"], cfg.atr_period)
    atr = np.r_[np.nan, atr[:-1]]
    prior_high = np.r_[np.nan, _rolling_max(market["high"], cfg.lookback)[:-1]]
    prior_low = np.r_[np.nan, _rolling_min(market["low"], cfg.lookback)[:-1]]
    vol_mean = np.r_[np.nan, _rolling_mean(market["volume"], cfg.volume_baseline)[:-1]]
    vol_pos = np.r_[np.nan, _rolling_mean((market["volume"] > 0).astype(float), cfg.volume_baseline)[:-1]]
    contiguous = _contiguous_mask(market["index"], cfg.lookback, cfg.bar_minutes)
    with np.errstate(divide="ignore", invalid="ignore"):
        rvol = market["volume"] / vol_mean
        bull_ext = (market["close"] - prior_high) / atr
        bear_ext = (prior_low - market["close"]) / atr
        bull_body = (market["close"] - market["open"]) / atr
        bear_body = (market["open"] - market["close"]) / atr
    valid = (
        contiguous
        & np.isfinite(atr) & (atr > 0)
        & np.isfinite(vol_mean) & (vol_mean > 0)
        & np.isfinite(vol_pos) & (vol_pos >= 0.8)
        & (market["volume"] > 0) & (market["close"] > 0)
        & np.isfinite(rvol) & (rvol >= cfg.rvol_min)
    )
    bull = valid & (bull_ext >= cfg.ext_min_atr) & (bull_ext <= cfg.ext_max_atr) & (bull_body >= cfg.body_min_atr)
    bear = valid & (bear_ext >= cfg.ext_min_atr) & (bear_ext <= cfg.ext_max_atr) & (bear_body >= cfg.body_min_atr)
    both = bull & bear
    bull = bull & ~both
    bear = bear & ~both
    previous_body = np.r_[np.nan, (market["close"] - market["open"])[:-1]] / atr
    bull = _kept_signals(bull, bull_ext, bull_body, rvol, previous_body, "BULLISH", cfg, market["rth"])
    bear = _kept_signals(bear, bear_ext, bear_body, rvol, previous_body, "BEARISH", cfg, market["rth"])
    signals = []
    for side, mask, extension, body in (
        ("BULLISH", bull, bull_ext, bull_body),
        ("BEARISH", bear, bear_ext, bear_body),
    ):
        for i in np.flatnonzero(mask):
            score = _score(float(rvol[i]), float(extension[i]), float(body[i]), float(previous_body[i]), side, cfg)
            if score < cfg.min_score:
                continue
            close_time = market["index"][i] + pd.Timedelta(minutes=cfg.bar_minutes)
            signals.append({
                "i": int(i),
                "direction": side,
                "price": float(market["close"][i]),
                "rvol": float(rvol[i]),
                "score": score,
                "atr": float(atr[i]),
                "extension_atr": float(extension[i]),
                "bar_time": close_time.isoformat(),
                "detector": config_name(cfg),
            })
    signals.sort(key=lambda row: row["i"])
    return signals


def _kept_signals(mask, extension, body, rvol, previous_body, direction: str, cfg: ExplosionConfig, rth: np.ndarray) -> np.ndarray:
    """Match assess_bars: score gate, then cooldown only among regular-hours emits."""
    raw = np.zeros(len(mask), dtype=bool)
    for i in np.flatnonzero(mask):
        if _score(float(rvol[i]), float(extension[i]), float(body[i]), float(previous_body[i]), direction, cfg) >= cfg.min_score:
            raw[i] = True
    return _cooldown(raw & rth, cfg.cooldown_bars)


def _score(rvol: float, extension: float, body: float, previous_body: float, direction: str, cfg: ExplosionConfig) -> int:
    room = (cfg.ext_max_atr - extension) / cfg.ext_max_atr
    if direction == "BULLISH":
        accel = 1.0 if body > previous_body else 0.0
    else:
        accel = 1.0 if body > -previous_body else 0.0
    if not np.isfinite(previous_body):
        accel = 0.0
    return int(min(100, round(
        25 * min(rvol / 3.0, 1.0)
        + 35 * max(0.0, room)
        + 25 * min(body / 1.0, 1.0)
        + 15 * accel
    )))


def _cooldown(mask: np.ndarray, cooldown: int) -> np.ndarray:
    out = np.zeros(len(mask), dtype=bool)
    last = -10**9
    for i in np.flatnonzero(mask):
        if i - last >= cooldown:
            out[i] = True
            last = int(i)
    return out


def scan_legacy(market: dict) -> list[dict]:
    """Vectorized assess_bars_legacy, restricted to regular-hours bars."""
    n = len(market["close"])
    if n < 32:
        return []
    atr = np.r_[np.nan, _rolling_mean(market["tr"], 14)[:-1]]
    prior_high = np.r_[np.nan, _rolling_max(market["high"], 30)[:-1]]
    prior_low = np.r_[np.nan, _rolling_min(market["low"], 30)[:-1]]
    vol_mean = np.r_[np.nan, _rolling_mean(market["volume"], 30)[:-1]]
    close = market["close"]
    shifted = np.r_[np.full(5, np.nan), close[:-5]]
    with np.errstate(divide="ignore", invalid="ignore"):
        momentum = close / shifted - 1.0
        rvol = market["volume"] / vol_mean
    valid = (
        market["rth"]
        & np.isfinite(atr) & (atr > 0)
        & np.isfinite(vol_mean) & (vol_mean > 0)
        & (market["volume"] > 0) & (close > 0)
        & np.isfinite(rvol) & np.isfinite(momentum)
        & np.isfinite(prior_high) & np.isfinite(prior_low)
    )
    bull = valid & (close > prior_high) & (momentum > 0) & (rvol >= 2.0) & (momentum >= 0.0035) & ((close - prior_high) >= 0.1 * atr)
    bear = valid & (close < prior_low) & (momentum < 0) & (rvol >= 2.0) & (-momentum >= 0.0035) & ((prior_low - close) >= 0.1 * atr)
    signals = []
    for i in np.flatnonzero(bull | bear):
        direction = "BULLISH" if bull[i] else "BEARISH"
        signals.append({
            "i": int(i),
            "direction": direction,
            "price": float(close[i]),
            "rvol": float(rvol[i]),
            "atr": float(atr[i]),
            "bar_time": (market["index"][i] + pd.Timedelta(minutes=5)).isoformat(),
            "detector": "legacy_30bar",
        })
    return signals


def build_events(market: dict) -> list[dict]:
    index = market["index"]
    high = market["high"]
    low = market["low"]
    close = market["close"]
    tr = market["tr"]
    rth = market["rth"]
    day = market["day"]
    n = len(close)
    events = []
    i = 16
    while i < n - 1:
        if not rth[i] or i < 15:
            i += 1
            continue
        if index[i] - index[i - 1] > pd.Timedelta(minutes=7):
            i += 1
            continue
        atr = float(tr[i - 14:i].mean())
        if not np.isfinite(atr) or atr <= 0:
            i += 1
            continue
        p0 = float(close[i - 1])
        target = max(TARGET_PCT * p0, TARGET_ATR_MULT * atr)
        end = i
        limit = min(n, i + HORIZON_BARS)
        while end < limit and day[end] == day[i] and (end == i or index[end] - index[end - 1] <= pd.Timedelta(minutes=7)):
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
        if direction == "BULLISH":
            extreme = float(high[onset:touch + 1].max())
        else:
            extreme = float(low[onset:touch + 1].min())
        events.append({
            "onset": int(onset),
            "touch": int(touch),
            "direction": direction,
            "p0": p0,
            "target": target,
            "extreme": extreme,
            "atr": atr,
            "day": day[onset],
            "onset_time": index[onset].isoformat(),
        })
        i = touch + 1
    return events


def _wilson(successes: int, trials: int, z: float = 1.96) -> list | None:
    if trials <= 0:
        return None
    phat = successes / trials
    den = 1 + z * z / trials
    center = (phat + z * z / (2 * trials)) / den
    margin = z * ((phat * (1 - phat) / trials + z * z / (4 * trials * trials)) ** 0.5) / den
    return [round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4)]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    return float(np.median(values))


def evaluate(signals: list[dict], events: list[dict], market: dict, sessions: list) -> dict:
    session_set = set(sessions)
    index = market["index"]
    high = market["high"]
    low = market["low"]
    close = market["close"]
    day = market["day"]
    kept_signals = [s for s in signals if market["day"][s["i"]] in session_set]
    kept_events = [e for e in events if e["day"] in session_set]
    used: set[int] = set()
    leads_onset = []
    leads_touch = []
    qualities = []
    early = 0
    before_done = 0
    matched = 0
    for event in kept_events:
        window = []
        for pos, signal in enumerate(kept_signals):
            if pos in used or signal["direction"] != event["direction"]:
                continue
            lead_min = (index[event["onset"]] - index[signal["i"]]).total_seconds() / 60.0
            if lead_min > MATCH_MINUTES:
                continue
            if signal["i"] > event["touch"]:
                continue
            window.append((signal["i"], pos, lead_min))
        if not window:
            continue
        window.sort()
        _, pos, _ = window[0]
        used.add(pos)
        signal = kept_signals[pos]
        lead_onset = (index[event["onset"]] - index[signal["i"]]).total_seconds() / 60.0
        lead_touch = (index[event["touch"]] - index[signal["i"]]).total_seconds() / 60.0
        if event["direction"] == "BULLISH":
            total = event["extreme"] - event["p0"]
            remaining = event["extreme"] - signal["price"]
        else:
            total = event["p0"] - event["extreme"]
            remaining = signal["price"] - event["extreme"]
        quality = remaining / total if total > 0 else 0.0
        matched += 1
        leads_onset.append(lead_onset)
        leads_touch.append(lead_touch)
        qualities.append(quality)
        if lead_onset > 0:
            early += 1
        if lead_touch > 0:
            before_done += 1
    if "hit_up" not in market:
        attach_outcomes(market)
    hits = 0
    scored = 0
    censored = 0
    for signal in kept_signals:
        i = signal["i"]
        if not market["horizon_ok"][i]:
            censored += 1
            continue
        scored += 1
        hit = market["hit_up"][i] if signal["direction"] == "BULLISH" else market["hit_down"][i]
        if hit:
            hits += 1
    up_hits = up_bars = down_hits = down_bars = 0
    for i in range(len(close)):
        if day[i] not in session_set or not market["rth"][i] or not market["horizon_ok"][i]:
            continue
        up_bars += 1
        down_bars += 1
        if market["hit_up"][i]:
            up_hits += 1
        if market["hit_down"][i]:
            down_hits += 1
    bull_n = sum(s["direction"] == "BULLISH" for s in kept_signals)
    bear_n = len(kept_signals) - bull_n
    up_rate = up_hits / up_bars if up_bars else 0.0
    down_rate = down_hits / down_bars if down_bars else 0.0
    if kept_signals:
        matched_base = (bull_n * up_rate + bear_n * down_rate) / len(kept_signals)
    else:
        matched_base = (up_rate + down_rate) / 2
    sessions_n = len(session_set)
    false_alarms = scored - hits
    return {
        "sessions": sessions_n,
        "start": sessions[0].isoformat() if sessions else None,
        "end": sessions[-1].isoformat() if sessions else None,
        "events": len(kept_events),
        "signals": len(kept_signals),
        "signals_per_session": round(len(kept_signals) / sessions_n, 4) if sessions_n else None,
        "matched_events": matched,
        "event_recall": round(matched / len(kept_events), 4) if kept_events else None,
        "event_recall_wilson95": _wilson(matched, len(kept_events)),
        "strictly_before_onset": early,
        "early_recall": round(early / len(kept_events), 4) if kept_events else None,
        "before_target_completion": before_done,
        "before_completion_recall": round(before_done / len(kept_events), 4) if kept_events else None,
        "median_lead_onset_min": None if _median(leads_onset) is None else round(_median(leads_onset), 2),
        "median_lead_touch_min": None if _median(leads_touch) is None else round(_median(leads_touch), 2),
        "median_entry_quality": None if _median(qualities) is None else round(_median(qualities), 4),
        "entry_quality_at_least_half": round(sum(q >= 0.5 for q in qualities) / len(qualities), 4) if qualities else None,
        "forward_hits": hits,
        "forward_scored_signals": scored,
        "forward_censored_signals": censored,
        "forward_hit_rate": round(hits / scored, 4) if scored else None,
        "forward_hit_wilson95": _wilson(hits, scored),
        "false_alarms": false_alarms,
        "false_alarms_per_session": round(false_alarms / sessions_n, 4) if sessions_n else None,
        "directional_base_rate": round(matched_base, 4),
        "up_base_rate": round(up_rate, 4),
        "down_base_rate": round(down_rate, 4),
    }


def _objective(row: dict) -> tuple:
    lead = row["median_lead_touch_min"]
    quality = row["median_entry_quality"]
    recall = row["before_completion_recall"]
    if lead is None or quality is None or recall is None:
        return (-1e9, 0, 0)
    return (lead + 15 * quality + 25 * recall, quality, -row["false_alarms_per_session"])


def gates_ok(row: dict, legacy: dict | None) -> bool:
    if row["signals"] < 8 or row["sessions"] < 5:
        return False
    if row["signals_per_session"] is None or row["signals_per_session"] > SIGNALS_PER_SESSION_MAX:
        return False
    if row["false_alarms_per_session"] is None or row["false_alarms_per_session"] > FA_PER_SESSION_MAX:
        return False
    if row["forward_hit_rate"] is None or row["directional_base_rate"] is None:
        return False
    if row["forward_hit_rate"] < 1.15 * row["directional_base_rate"]:
        return False
    if row["median_entry_quality"] is None or row["median_entry_quality"] < 0.45:
        return False
    if row["median_lead_touch_min"] is None or row["median_lead_touch_min"] < 0:
        return False
    if legacy and legacy["median_lead_touch_min"] is not None:
        if row["median_lead_touch_min"] < legacy["median_lead_touch_min"]:
            return False
    return True


def select_config(validation_rows: list[dict], legacy_validation: dict) -> dict:
    eligible = [row for row in validation_rows if gates_ok(row, legacy_validation)]
    if not eligible:
        return {"selected": None, "gates_met": False, "eligible": 0}
    eligible.sort(key=_objective, reverse=True)
    winner = eligible[0]
    return {
        "selected": winner["name"],
        "gates_met": True,
        "eligible": len(eligible),
        "objective": _objective(winner)[0],
    }


def split_sessions(sessions: list) -> dict[str, list]:
    n = len(sessions)
    n_test = max(1, n // 5)
    n_val = max(1, n // 5)
    if n_test + n_val >= n:
        n_test = max(1, n // 5)
        n_val = max(1, n // 5)
    return {
        "train": sessions[:n - n_val - n_test],
        "validation": sessions[n - n_val - n_test:n - n_test],
        "holdout": sessions[-n_test:],
    }


def evaluate_detector(signals: list[dict], events: list[dict], market: dict, parts: dict) -> dict:
    return {name: evaluate(signals, events, market, days) for name, days in parts.items()}


def run_comparison(bars: pd.DataFrame, symbol: str, preset: ExplosionConfig | None = None) -> dict:
    """Select on this symbol's validation slice. Holdout is scored after selection."""
    preset = preset or ExplosionConfig()
    market = attach_outcomes(prepare_market(drop_partial_last_session(bars)))
    sessions = complete_sessions(market)
    parts = split_sessions(sessions)
    events = build_events(market)
    legacy_signals = scan_legacy(market)
    legacy = evaluate_detector(legacy_signals, events, market, parts)
    rows = []
    scanned: dict[str, list[dict]] = {}
    for cfg in config_grid():
        name = config_name(cfg)
        signals = scan_early(market, cfg)
        scanned[name] = signals
        metrics = evaluate(signals, events, market, parts["validation"])
        metrics["name"] = name
        metrics["config"] = config_payload(cfg)
        rows.append(metrics)
    choice = select_config(rows, legacy["validation"])
    selected_name = choice["selected"] or config_name(preset)
    selected_cfg = next(cfg for cfg in config_grid() if config_name(cfg) == selected_name)
    selected_signals = scanned[selected_name]
    selected = evaluate_detector(selected_signals, events, market, parts)
    preset_name = config_name(preset)
    preset_metrics = evaluate_detector(scanned[preset_name], events, market, parts) if preset_name in scanned else None
    fresh_cut = datetime(2026, 11, 4).date()
    fresh_days = [day for day in sessions if day > fresh_cut]
    fresh = {
        "selected": evaluate(selected_signals, events, market, fresh_days) if fresh_days else None,
        "legacy": evaluate(legacy_signals, events, market, fresh_days) if fresh_days else None,
        "note": "Sessions after 2026-11-04 were not used by the breadth study's consumed prefix. Too few to select on; reported only.",
    }
    return {
        "symbol": symbol,
        "event": {
            "target": "max(0.30% of anchor close, 3 x prior 14-bar ATR)",
            "horizon_bars": HORIZON_BARS,
            "horizon_minutes": HORIZON_BARS * 5,
            "onset": "first bar covering 25% of the target; that bar must be the event start",
            "entry_quality": "(extreme through target touch - signal close) / (extreme - anchor close), signed with direction",
            "lead_onset_min": "onset bar start minus signal bar start; positive means the signal bar began first",
            "lead_touch_min": "target-touch bar start minus signal bar start",
        },
        "splits": {name: [day.isoformat() for day in days] for name, days in parts.items()},
        "selection": choice,
        "selected_name": selected_name,
        "decision": {
            "promote_early": False,
            "live_mode": "legacy",
            "reason": (
                "The validation-selected early range release is reported against legacy on the "
                "untouched holdout and is not installed as the alert path. Promotion would require "
                "a better holdout lead and entry quality without collapsing recall or forward hit rate."
            ),
        },
        "selected_config": config_payload(selected_cfg),
        "selected": selected,
        "preset": preset_metrics,
        "legacy": legacy,
        "validation_grid": rows,
        "unconsumed_after_2026_11_04": fresh,
    }


def arabic_holdout_paragraph(report: dict) -> str:
    selected = report["selected"]["holdout"]
    legacy = report["legacy"]["holdout"]
    return (
        "لم يُعتمد كاشف الدخول المبكر في التنبيه الحي. "
        f"على اختبار {report['symbol']} المعزول ({selected['start']} إلى {selected['end']}، "
        f"{selected['sessions']} جلسات، {selected['events']} انفجارات) الإعداد {report['selected_name']} "
        f"التقط {selected['before_completion_recall']} من الانفجارات قبل اكتمال الهدف، "
        f"بوسيط سبق {selected['median_lead_touch_min']} دقيقة وجودة دخول {selected['median_entry_quality']} "
        f"ومعدل إصابة أمامي {selected['forward_hit_rate']}. "
        f"القاعدة القديمة التقطت {legacy['before_completion_recall']} بوسيط سبق {legacy['median_lead_touch_min']} دقيقة "
        f"وجودة {legacy['median_entry_quality']} ومعدل إصابة {legacy['forward_hit_rate']}. "
        "التنبيه الافتراضي يبقى تأكيد الشمعة المكتملة. التجربة المبكرة تُفعّل فقط بـ EXPLOSION_MODE=early، "
        "وهذه أرقام على حركة الأصل وليست عائد خيار."
    )


def fetch_yahoo(symbol: str, rng: str = "60d") -> pd.DataFrame:
    import json as _json
    import urllib.parse
    import urllib.request

    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
        f"?interval=5m&range={rng}&includePrePost=true"
    )
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research)"})
    with urllib.request.urlopen(request, timeout=40) as response:
        document = _json.loads(response.read())
    result = document["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    frame = pd.DataFrame(
        {
            "Open": quote["open"], "High": quote["high"], "Low": quote["low"],
            "Close": quote["close"], "Volume": quote["volume"],
        },
        index=pd.to_datetime(result["timestamp"], unit="s", utc=True),
    )
    frame = frame.dropna().astype(float)
    frame = frame[~frame.index.duplicated(keep="last")].sort_index()
    if frame.empty:
        raise RuntimeError(f"no bars for {symbol}")
    frame = frame.loc[frame.index + pd.Timedelta(minutes=5) <= frame.index[-1]]
    frame.attrs["source"] = "Yahoo chart 5m includePrePost; research delay, not a live IBKR archive"
    return frame


def _load(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="No-orders historical signal study")
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--period", default="1mo", choices=["5d", "1mo"])
    parser.add_argument("--horizon", type=int, default=6)
    parser.add_argument("--output", default="backtest_results.json")
    parser.add_argument("--input", help="Saved OHLCV csv/gz. Switches on the early-vs-legacy comparison.")
    parser.add_argument("--transfer", action="append", default=[], help="symbol=path scored with the selected config, no re-selection")
    parser.add_argument("--fetch-yahoo", action="store_true", help="Download SPY, QQQ and ^GSPC 5m bars, then compare")
    parser.add_argument("--save-dir", help="Directory for fetched bars and the comparison report")
    args = parser.parse_args()
    if args.fetch_yahoo or args.input:
        save_dir = Path(args.save_dir) if args.save_dir else None
        if args.fetch_yahoo:
            if save_dir is None:
                raise SystemExit("--save-dir is required with --fetch-yahoo")
            save_dir.mkdir(parents=True, exist_ok=True)
            paths = {}
            for symbol in ("SPY", "QQQ", "^GSPC"):
                frame = fetch_yahoo(symbol)
                path = save_dir / f"{symbol.replace('^', '')}_5m.csv.gz"
                frame.to_csv(path)
                paths[symbol] = path
            primary_path = paths["SPY"]
            transfers = [f"{symbol}={path}" for symbol, path in paths.items() if symbol != "SPY"]
        else:
            primary_path = Path(args.input)
            transfers = list(args.transfer)
        primary = run_comparison(_load(primary_path), args.symbol if not args.fetch_yahoo else "SPY")
        selected = ExplosionConfig(**{
            key: value for key, value in primary["selected_config"].items() if key != "max_bar_age_minutes"
        })
        # max_bar_age was removed from the payload's timedelta; restore the default.
        transfer_reports = []
        for item in transfers:
            symbol, path = item.split("=", 1)
            market = attach_outcomes(prepare_market(drop_partial_last_session(_load(Path(path)))))
            sessions = complete_sessions(market)
            parts = split_sessions(sessions)
            events = build_events(market)
            transfer_reports.append({
                "symbol": symbol,
                "role": "transfer_no_reselection",
                "splits": {name: [day.isoformat() for day in days] for name, days in parts.items()},
                "selected": evaluate_detector(scan_early(market, selected), events, market, parts),
                "legacy": evaluate_detector(scan_legacy(market), events, market, parts),
            })
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "primary": primary,
            "transfer": transfer_reports,
            "summary_ar": arabic_holdout_paragraph(primary),
            "limits": [
                "Decision time is the completed 5-minute bar close. A slower feed reduces lead by its delay.",
                "Yahoo chart history can be revised and is not an IBKR receipt-time archive.",
                "Underlying path only. No SPX option premium, spread, slippage, or commission.",
                "The technical score is uncalibrated and is not a probability.",
                "Training inspection found no lift for volatility-compression gates, so compression is not required.",
                "Validation on SPY selects the config. Holdout and the other symbols are not used to choose it.",
                "Earlier ES/NQ and breadth studies overlap part of this calendar. The post-2026-11-04 slice is reported separately and is small.",
                "Five-minute closes cannot see inside the signal bar.",
            ],
        }
        destination = Path(args.output)
        if save_dir is not None and args.output == "backtest_results.json":
            destination = save_dir / "report.json"
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(payload["summary_ar"])
        return
    bars = market_data.Ticker(args.symbol).history(
        period=args.period, interval="5m", auto_adjust=False, require_realtime=False
    )
    if bars.empty:
        raise SystemExit("No market data: no result produced")
    outcome = study(args.symbol, bars, args.horizon)
    Path(args.output).write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in outcome.items() if k != "sample"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
