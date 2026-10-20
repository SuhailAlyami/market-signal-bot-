"""Causal, experimental option-premium WATCH/ACCELERATION observations.

These are option TRADE bars, not executable bid/ask quotes. No order or
notification is enabled. Thresholds are fixed research hypotheses, not a
calibrated probability or a demonstrated predictive edge.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

MINUTE = timedelta(minutes=1)


def history_frame(raw):
    """Normalize IBKR's actual parallel arrays without filling missing bars."""
    if raw.get("error") or raw.get("chart_step") != 60:
        raise ValueError("one_minute_history_required")
    keys = ("time", "open", "high", "low", "close", "volume")
    if not all(isinstance(raw.get(key), list) for key in keys):
        raise ValueError("missing_ohlcv_arrays")
    if len({len(raw[key]) for key in keys}) != 1:
        raise ValueError("mismatched_history_arrays")
    index = pd.DatetimeIndex(raw["time"])
    if index.tz is None or index.has_duplicates or not index.is_monotonic_increasing:
        raise ValueError("invalid_history_clock")
    return pd.DataFrame({key.title(): raw[key] for key in keys[1:]}, index=index.tz_convert("UTC"))


def features(data, i):
    """Use exactly 20 past bars plus current completed bar; reject gaps/errors."""
    if i < 20 or i >= len(data) or not isinstance(data.index, pd.DatetimeIndex) or data.index.tz is None:
        return None
    sample = data.iloc[i-20:i+1]
    if sample.index.has_duplicates or not (sample.index.to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all():
        return None
    required = ["Open", "High", "Low", "Close", "Volume"]
    if any(key not in sample for key in required):
        return None
    try:
        valid = sample[required].apply(lambda column: column.map(
            lambda x: isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)))
        if not valid.all().all():
            return None
        if ((sample[["Open", "High", "Low", "Close"]] <= 0).any().any()
                or (sample.Volume < 0).any()
                or (sample.High < sample[["Open", "Close"]].max(axis=1)).any()
                or (sample.Low > sample[["Open", "Close"]].min(axis=1)).any()
                or (sample.High < sample.Low).any()):
            return None
        prior, last = sample.iloc[:-1], sample.iloc[-1]
        if (prior.Volume > 0).sum() < 12 or last.Volume <= 0 or last.Close < 1:
            return None
        ranges = prior.High - prior.Low
        typical = float(ranges[ranges > 0].median())
        average_volume = float(prior.Volume.mean())
        if not math.isfinite(typical) or typical <= 0 or average_volume <= 0:
            return None
        previous = float(prior.Close.iloc[-1])
        returns = prior.Close.pct_change().abs().dropna()
        typical_return = float(returns.median())
        if not math.isfinite(typical_return):
            return None
        return {"price": float(last.Close), "prior_high": float(prior.High.max()),
                "prior_low": float(prior.Low.min()), "range": typical,
                "rvol": float(last.Volume / average_volume),
                "return_1m": float(last.Close / previous - 1),
                "return_3m": float(last.Close / prior.Close.iloc[-3] - 1),
                "typical_return": typical_return,
                "recent_range": float(prior.High.iloc[-3:].max() - prior.Low.iloc[-3:].min()),
                "invalidation": float(sample.Low.iloc[-3:].min())}
    except (ValueError, TypeError, OverflowError):
        return None


def classify(data, i):
    f = features(data, i)
    return classify_features(f, data.index[i].to_pydatetime() + MINUTE) if f is not None else None


def classify_features(f, bar_end):
    if f is None:
        return None
    distance = (f["prior_high"] - f["price"]) / f["range"]
    # WATCH is below the old high. ACCELERATION is the first qualifying minute
    # beyond it, not a claim to have predicted the move before it began.
    accelerating = (f["price"] > f["prior_high"] and f["rvol"] >= 1.5
                    and f["return_1m"] >= max(0.03, 1.5 * f["typical_return"]))
    preparing = (0 <= distance <= 0.75 and f["recent_range"] <= 1.5 * f["range"]
                 and f["return_1m"] > 0 and f["return_3m"] > 0 and f["rvol"] >= 1.2)
    if not accelerating and not preparing:
        return None
    state = "ACCELERATION" if accelerating else "WATCH"
    return {"state": state, "state_ar": "تسارع علاوة مرصود" if accelerating else "استعداد علاوة محتمل",
            "bar_end": bar_end.isoformat(),
            "reference_trade_price": f["price"], "breakout_level": f["prior_high"],
            "invalidation_reference": f["invalidation"], "rvol": round(f["rvol"], 4),
            "return_1m_pct": round(f["return_1m"] * 100, 4),
            "probability": None, "research_only": True, "notifications_enabled": False,
            "execution_price": None}


def assess_history(raw, *, now=None, feed_status="UNAVAILABLE"):
    """Runtime boundary: completed, recent bars and explicit feed status only."""
    now = now or datetime.now(timezone.utc)
    result = {"status": "unavailable", "signal": None, "research_only": True,
              "notifications_enabled": False, "historical_delayed": raw.get("delayed")}
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("aware_clock_required")
    try:
        data = history_frame(raw)
        # Treat provider timestamps conservatively as bar START, never as a
        # completed bar at that same timestamp.
        data = data[data.index + pd.Timedelta(minutes=1) <= now]
        if len(data) < 21:
            return {**result, "reason": "insufficient_completed_bars"}
        end = data.index[-1].to_pydatetime() + MINUTE
        elapsed = (now - end).total_seconds()
        result.update(last_completed_bar=end.isoformat(), bar_age_seconds=elapsed)
        if feed_status != "REALTIME" or raw.get("delayed") not in (None, 0, False):
            return {**result, "reason": "feed_not_realtime"}
        if not 0 <= elapsed <= 120:
            return {**result, "reason": "stale_history"}
        if features(data, len(data)-1) is None:
            return {**result, "reason": "invalid_or_illiquid_window"}
        return {**result, "status": "observed", "reference_trade_price": float(data.Close.iloc[-1]),
                "signal": classify(data, len(data)-1),
                "reason": "experimental_trade_bar_observation_not_executable_quote"}
    except (ValueError, TypeError, KeyError, OverflowError):
        return {**result, "reason": "invalid_history"}


def journal_observations(report, directory):
    """Persist at-most-once observations/cancellations; never send alerts.

    Reserve IDs before appending: a disk failure may omit an event, but a retry
    cannot silently duplicate an already reserved event. Corrupt state raises.
    """
    from ibkr_mcp import save_report
    directory = Path(directory)
    state_path, journal = directory / "premium_state.json", directory / "premium_shadow.jsonl"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"seen": [], "active": {}, "last": {}}
    if not isinstance(state.get("seen"), list) or not isinstance(state.get("active"), dict) or not isinstance(state.get("last"), dict):
        raise ValueError("invalid_premium_journal_state")
    now = datetime.fromisoformat(report["observed_at"])
    pending = []
    items = list(report.get("premium_radar", []))
    present = {f"{item['expiry']}:{item['strike']}:{item['side']}" for item in items}
    for key in state["active"]:
        if key not in present:
            expiry, strike, side = key.split(":")
            items.append({"expiry": expiry, "strike": float(strike), "side": side,
                          "status": "unavailable", "signal": None})
    for item in items:
        key = f"{item['expiry']}:{item['strike']}:{item['side']}"
        signal, active = item.get("signal"), state["active"].get(key)
        phase, reason = None, None
        if active:
            old = datetime.fromisoformat(active["started_at"])
            broken = (item.get("status") != "observed" or now - old >= timedelta(minutes=10)
                      or item.get("reference_trade_price", float("inf")) <= active["invalidation"])
            if broken:
                phase, reason = "INVALIDATION", "stale_illiquid_expired_or_level_crossed"
                state["active"].pop(key)
        if phase is None and signal:
            phase = signal["state"]
            prospective_id = hashlib.sha256(f"{key}:{phase}:{item.get('last_completed_bar')}".encode()).hexdigest()[:24]
            if prospective_id in state["seen"]:
                continue
            previous = state["last"].get(key)
            if previous and phase == "WATCH" and now - datetime.fromisoformat(previous) < timedelta(minutes=5):
                continue
            if active and active["state"] == phase:
                continue
            state["active"][key] = {"state": phase, "started_at": active["started_at"] if active else now.isoformat(),
                                    "invalidation": signal["invalidation_reference"]}
            state["last"][key] = now.isoformat()
            reason = "experimental_premium_observation"
        if phase is None:
            continue
        bar_end = item.get("last_completed_bar")
        event_id = hashlib.sha256(f"{key}:{phase}:{bar_end}".encode()).hexdigest()[:24]
        if event_id in state["seen"]:
            continue
        state["seen"].append(event_id)
        pending.append({"event_id": event_id, "state": phase, "reason": reason,
                        "expiry": item["expiry"], "strike": item["strike"], "side": item["side"],
                        "bar_end": bar_end, "detected_at": now.isoformat(),
                        "reference_trade_price": item.get("reference_trade_price"),
                        "research_only": True, "notifications_enabled": False, "execution_price": None})
    state["seen"] = state["seen"][-2000:]
    # Remove expired contracts without resetting today's deduplication state.
    today = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    state["active"] = {key: value for key, value in state["active"].items() if key.split(":")[0] >= today}
    save_report(state, state_path)
    if pending:
        fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as stream:
            for event in pending:
                stream.write(json.dumps(event, allow_nan=False, ensure_ascii=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    return pending
