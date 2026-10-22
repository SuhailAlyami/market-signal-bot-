"""Single, fail-closed 1m underlying research runtime. No orders or option quotes.

The experimental detector is shared with the chronological research harness.
Canonical events remain research-only. Explicitly authorized ES rule alerts are
assembled and gated separately; they do not imply an out-of-sample edge.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from strategy_rules import CONFIRM_BARS,BUFFER_ATR,EXPIRY_MINUTES,COOLDOWN_MINUTES

UTC = timezone.utc
NY = ZoneInfo("America/New_York")
BAR = timedelta(minutes=1)
MAX_AGE = timedelta(minutes=2)
SOURCE = "IBKR native market data; realtime status validated by data adapter"
ARABIC_STATES = {"SETUP": "استعداد", "TRIGGER": "دخول مشروط", "INVALIDATION": "إلغاء", "EXIT": "خروج"}


def utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(UTC)


@lru_cache(maxsize=16)
def _futures_schedule(day):
    import pandas_market_calendars as mcal

    # Sunday evening belongs to Monday's trading session.
    return mcal.get_calendar("CME_Equity").schedule(
        start_date=day, end_date=day + timedelta(days=2))


def futures_active(now: datetime) -> bool:
    """CME equity calendar includes DST, holidays, early closes and intraday halt.

    A missing/broken calendar raises rather than silently treating holidays as
    open. The polling boundary records the failure and suppresses detection.
    """
    now = utc(now)
    for _, row in _futures_schedule(now.astimezone(NY).date()).iterrows():
        if row.market_open <= now < row.market_close:
            if "break_start" in row and pd.notna(row.break_start) and row.break_start <= now < row.break_end:
                return False
            return True
    return False


def validate_completed_bars(frame: pd.DataFrame, now: datetime, min_bars: int = 31):
    """Return a contiguous valid tail and explicit status; bar index is START.

    Measured delay is time since the last completed candle, not verified
    exchange-to-provider latency. An unfinished current bar is never inspected
    for decisions. Older session gaps do not poison a contiguous current tail.
    """
    now = utc(now)
    status = {"status": "unavailable", "last_completed_bar": None,
              "detection_delay_seconds": None, "source": SOURCE, "live_feed_verified": False}
    def reject(reason):
        status["status"] = reason
        return None, status

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return reject("empty_feed")
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        return reject("naive_or_invalid_timestamps")
    if frame.index.has_duplicates:
        return reject("duplicate_timestamps")
    index_prices = (frame.attrs.get('symbol')=='SPX' and frame.attrs.get('security_type')=='IND'
                    and frame.attrs.get('source')=='IBKR Gateway TWS API')
    required = ["Open", "High", "Low", "Close"] + ([] if index_prices else ["Volume"])
    if any(col not in frame for col in required):
        return reject("missing_ohlcv")
    data = frame.sort_index().copy()
    data.index = data.index.tz_convert("UTC")
    data = data[data.index + BAR <= pd.Timestamp(now)]
    if data.empty:
        return reject("no_completed_bars")
    end = data.index[-1].to_pydatetime() + BAR
    status.update(last_completed_bar=end.isoformat(), detection_delay_seconds=(now - end).total_seconds())
    if now - end > MAX_AGE:
        return reject("stale_feed")
    # Never fill missing market observations or turn missing volume into zero.
    if any(ts.second or ts.microsecond for ts in data.index[-min_bars:]):
        return reject("unaligned_bars")
    differences = data.index.to_series().diff()
    gaps = differences[differences != pd.Timedelta(BAR)].index
    tail = data.loc[gaps[-1]:] if len(gaps) else data
    if len(tail) < min_bars:
        return reject("warming_up_or_gap")
    recent = tail.iloc[-min_bars:]
    try:
        values = recent[required].astype(float)
    except (TypeError, ValueError):
        return reject("invalid_ohlcv")
    if not all(math.isfinite(float(value)) for value in values.to_numpy().flat):
        return reject("nonfinite_ohlcv")
    if not index_prices and (values.Volume <= 0).any():
        return reject("zero_or_negative_volume")
    if (values[["Open", "High", "Low", "Close"]] <= 0).any().any():
        return reject("nonpositive_price")
    if ((values.High < values[["Open", "Close", "Low"]].max(axis=1)) |
            (values.Low > values[["Open", "Close", "High"]].min(axis=1))).any():
        return reject("inconsistent_ohlc")
    status["status"] = "ok"
    return data, status


def experimental_candidate(bars: pd.DataFrame, index: int):
    """Use precisely the causal research rule, without implying a verified edge."""
    from strategy_rules import candidate
    return candidate(bars,index)


class HunterRuntime:
    """Persist dedupe/lifecycle and observable shadow decisions independently of delivery.

    Files survive process restarts on the same filesystem. Render's default
    ephemeral filesystem does NOT guarantee survival across replacement or
    redeploy; this limitation is reported and notifications remain disabled.
    """
    def __init__(self, state_path, journal_path, symbols=("ES=F", "NQ=F"), detector=None):
        self.state_path, self.journal_path = Path(state_path), Path(journal_path)
        self.symbols = tuple(symbols)
        self.detector = detector or experimental_candidate
        self.price_context_status = {}
        self.state = {"version": 1, "symbols": {}, "pending": [], "notifications": {}}
        self.persistence_error = None
        try:
            if self.state_path.exists():
                loaded = json.loads(self.state_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict) or loaded.get("version") != 1 or not isinstance(loaded.get("symbols"), dict):
                    raise ValueError("invalid state schema")
                if not isinstance(loaded.get("pending"), list) or not isinstance(loaded.get("notifications"), dict):
                    raise ValueError("invalid state schema")
                for item in loaded["symbols"].values():
                    if not isinstance(item, dict):
                        raise ValueError("invalid symbol state")
                    for key in ("last_bar_end", "cooldown_until"):
                        if item.get(key):
                            utc(datetime.fromisoformat(item[key]))
                    active = item.get("active")
                    if active:
                        if not isinstance(active, dict) or active.get("phase") not in ("SETUP", "TRIGGER"):
                            raise ValueError("invalid active state")
                        if active.get("direction") not in (-1, 1):
                            raise ValueError("invalid direction")
                        utc(datetime.fromisoformat(active["started_at"]))
                        if not all(math.isfinite(float(active[key])) for key in ("level", "invalidation", "atr")):
                            raise ValueError("invalid scenario prices")
                for item in loaded["pending"]:
                    if not isinstance(item, dict) or not all(key in item for key in
                            ("event_id", "symbol", "bar_end", "detected_at", "outcome_start", "price", "direction", "horizon_minutes")):
                        raise ValueError("invalid pending observation")
                    utc(datetime.fromisoformat(item["bar_end"]))
                    utc(datetime.fromisoformat(item["detected_at"]))
                    utc(datetime.fromisoformat(item["outcome_start"]))
                    if item["direction"] not in (-1, 1) or item["horizon_minutes"] != 5 or not math.isfinite(float(item["price"])):
                        raise ValueError("invalid pending observation")
                self.state = loaded
        except (OSError, ValueError, TypeError, KeyError):
            # Do not reset corrupt dedupe state and silently emit repeated events.
            self.persistence_error = "state_unreadable"

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(self.state, handle, allow_nan=False, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.state_path)

    def _record(self, entry):
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        with self.journal_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, allow_nan=False, ensure_ascii=False) + "\n")
            handle.flush()

    def _event(self, symbol, phase, scenario, now, bar_end, price, reason):
        key = f"{symbol}:{phase}:{bar_end}:{scenario['started_at']}"
        event = {"schema_version": 1, "record_type": "event", "event_id": hashlib.sha256(key.encode()).hexdigest()[:24],
                 "symbol": symbol, "state": phase, "state_ar": ARABIC_STATES[phase],
                 "direction": "UP" if scenario["direction"] > 0 else "DOWN",
                 "bar_end": bar_end, "detected_at": now.isoformat(), "price": price,
                 "level": scenario["level"], "invalidation": scenario["invalidation"],
                 "rvol": scenario.get("rvol"), "reason": reason, "source": SOURCE,
                 "analysis_only": True, "live_feed_verified": False, "readiness": "NOT_READY",
                 "detector": "experimental.pre_level", "confidence_probability": None,
                 "confidence_status": "uncalibrated", "notify_eligible": False}
        if bar_end:
            end = datetime.fromisoformat(bar_end)
            event["bar_start"] = (end - BAR).isoformat()
            event["detection_delay_seconds"] = (now - end).total_seconds()
        self._record(event)
        if phase in ("SETUP", "TRIGGER"):
            self.state["pending"].append({"event_id": event["event_id"], "symbol": symbol,
                                          "bar_end": bar_end, "price": price,
                                          "detected_at": now.isoformat(),
                                          "outcome_start": pd.Timestamp(now).ceil("min").isoformat(),
                                          "direction": scenario["direction"], "horizon_minutes": 5})
        return event

    def _resolve_outcomes(self, symbol, data, now):
        remaining = []
        for item in self.state["pending"]:
            if item["symbol"] != symbol:
                remaining.append(item)
                continue
            # A delayed candle cannot earn returns from before its actual
            # detection. Observe five full minutes beginning at the next minute
            # boundary, using its Open as a diagnostic reference, never a fill.
            outcome_start = pd.Timestamp(item["outcome_start"])
            target_end = outcome_start + pd.Timedelta(minutes=item["horizon_minutes"])
            future = data[(data.index >= outcome_start) & (data.index + BAR <= target_end)]
            if len(future) != item["horizon_minutes"] or future.index[-1] + BAR != target_end:
                # At a session gap the five-minute outcome is unobservable, not a loss/zero.
                if data.index[-1] + BAR > target_end + pd.Timedelta(minutes=5):
                    self._record({"record_type": "outcome", **item, "observed_at": now.isoformat(),
                                  "status": "unobservable_gap", "underlying_return_bps": None})
                else:
                    remaining.append(item)
                continue
            _, outcome_status = validate_completed_bars(future, target_end.to_pydatetime(),
                                                        min_bars=item["horizon_minutes"])
            if outcome_status["status"] != "ok":
                self._record({"record_type": "outcome", **item, "observed_at": now.isoformat(),
                              "status": "unobservable_invalid_bars", "underlying_return_bps": None})
                continue
            direction, entry = item["direction"], float(future.Open.iloc[0])
            terminal = float(future.Close.iloc[-1])
            best = float(future.High.max()) if direction > 0 else float(future.Low.min())
            worst = float(future.Low.min()) if direction > 0 else float(future.High.max())
            self._record({"record_type": "outcome", **item, "observed_at": now.isoformat(),
                          "status": "observed", "outcome_bar_end": target_end.isoformat(),
                          "outcome_timing": "five_full_minutes_after_detection_boundary",
                          "entry_reference_price": entry, "entry_reference_is_fill": False,
                          "underlying_return_bps": direction * (terminal / entry - 1) * 10000,
                          "favorable_excursion_bps": direction * (best / entry - 1) * 10000,
                          "adverse_excursion_bps": direction * (worst / entry - 1) * 10000,
                          "option_pnl": None, "execution_assumed": False})
        self.state["pending"] = remaining

    def _cancel(self, symbol, now, status, reason):
        state = self.state["symbols"].setdefault(symbol, {})
        active = state.pop("active", None)
        if not active:
            return []
        state["cooldown_until"] = (now + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
        # Missing prices never create synthetic fills, terminal returns or P&L.
        return [self._event(symbol, "EXIT" if active["phase"] == "TRIGGER" else "INVALIDATION",
                            active, now, status.get("last_completed_bar") or state.get("last_bar_end"),
                            None, reason)]

    def reject_plan(self, event, reason):
        """Release only the rejected trigger, never a newer scenario or dedupe.

        A strategy/risk rejection is not an entered position and earns no
        position lifetime or cooldown. Durable bar dedupe still forbids replay.
        """
        if event.get('state') != 'TRIGGER' or self.persistence_error:
            return False
        state = self.state['symbols'].get(event.get('symbol'), {})
        active = state.get('active')
        if not active or active.get('phase') != 'TRIGGER':
            return False
        key = f"{event['symbol']}:TRIGGER:{event.get('bar_end')}:{active['started_at']}"
        if hashlib.sha256(key.encode()).hexdigest()[:24] != event.get('event_id'):
            return False
        state.pop('active')
        try:
            self._record({'record_type':'plan_rejection','event_id':event['event_id'],
                'symbol':event['symbol'],'bar_end':event['bar_end'],'reason':reason,
                'next_state':'READY','analysis_only':True,'execution_assumed':False})
            self._save()
        except (OSError,ValueError,TypeError):
            self.persistence_error = 'persistence_failed'
            return False
        return True

    def _process_bar(self, symbol, data, index, now):
        state = self.state["symbols"].setdefault(symbol, {})
        row = data.iloc[index]
        end = (data.index[index].to_pydatetime() + BAR).isoformat()
        if state.get("last_bar_end") and end <= state["last_bar_end"]:
            return []
        price, events = float(row.Close), []
        active = state.get("active")
        if active:
            elapsed = datetime.fromisoformat(end) - datetime.fromisoformat(active["started_at"])
            direction = active["direction"]
            invalid = direction * (price - active["invalidation"]) <= 0
            if invalid or elapsed >= timedelta(minutes=EXPIRY_MINUTES):
                phase = "EXIT" if active["phase"] == "TRIGGER" else "INVALIDATION"
                events.append(self._event(symbol, phase, active, now, end, price,
                                          "invalidation_crossed" if invalid else "scenario_expired"))
                state.pop("active")
                state["cooldown_until"] = (datetime.fromisoformat(end) + timedelta(minutes=COOLDOWN_MINUTES)).isoformat()
            elif active["phase"] == "SETUP":
                # Two distinct closes beyond a 0.1 ATR buffer avoid single-tick churn.
                beyond = direction * (price - active["level"]) >= BUFFER_ATR * active["atr"]
                active["confirmation_bars"] = active.get("confirmation_bars", 0) + 1 if beyond else 0
                if active["confirmation_bars"] >= CONFIRM_BARS:
                    active["phase"] = "TRIGGER"
                    events.append(self._event(symbol, "TRIGGER", active, now, end, price, "two_buffered_closes"))
        else:
            candidate = self.detector(data, index)
            cooled = not state.get("cooldown_until") or end >= state["cooldown_until"]
            if candidate and cooled:
                active = {**candidate, "phase": "SETUP", "started_at": end, "confirmation_bars": 0}
                state["active"] = active
                events.append(self._event(symbol, "SETUP", active, now, end, price, "experimental_causal_setup"))
        state["last_bar_end"] = end
        # Research annotation cannot create/suppress lifecycle events or delivery.
        try:
            from price_action_context import observe
            price_context = observe(data, index)
        except Exception as exc:
            price_context = {"status": "context_error", "error_type": type(exc).__name__,
                             "mode": "SHADOW", "notify_eligible": False}
        self.price_context_status[symbol] = {
            "version": price_context.get("version"), "status": price_context["status"],
            "last_bar_end": end, "mode": "SHADOW", "notify_eligible": False}
        self._record({"record_type": "observation", "symbol": symbol, "bar_end": end,
                      "detected_at": now.isoformat(), "decision": events[-1]["state"] if events else "NO_TRANSITION",
                      "active_state": state.get("active", {}).get("phase"), "price": price,
                      "price_action_context": price_context,
                      "analysis_only": True, "source": SOURCE, "notify_eligible": False})
        return events

    def poll(self, now: datetime, fetcher, clock=None):
        """Always evaluate every symbol; outbound delivery limits cannot gate this.

        fetcher(symbol) returns OHLCV 1m bars. It must raise on provider failure;
        the heartbeat distinguishes unavailable, stale, warm-up and closed feeds.
        """
        now = utc(now)
        started = now
        receipt_time = (lambda: utc(clock())) if clock else (lambda: started)
        heartbeat = {"record_type": "heartbeat", "timestamp": now.isoformat(), "status": "ok",
                     "poll_started_at": now.isoformat(),
                     "alerts_enabled": False, "readiness": "NOT_READY", "symbols": {},
                     "state_backend": "local_atomic_json", "persistence_guaranteed": False,
                     "persistence_note": "survives same-filesystem restart; ephemeral Render replacement may erase state"}
        events = []
        if self.persistence_error:
            heartbeat["status"] = self.persistence_error
            return {"events": events, "heartbeat": heartbeat}
        try:
            active = futures_active(now)
        except Exception as exc:
            active = False
            heartbeat["status"] = "calendar_unavailable"
            heartbeat["error_type"] = type(exc).__name__
        try:
            for symbol in self.symbols:
                now = receipt_time()
                previous = self.state["symbols"].get(symbol, {})
                if not active:
                    status = {"status": "closed" if heartbeat["status"] == "ok" else "calendar_unavailable",
                              "last_completed_bar": previous.get("last_bar_end")}
                    events.extend(self._cancel(symbol, now, status, "market_closed_or_calendar_unavailable"))
                else:
                    try:
                        frame = fetcher(symbol)
                        now = receipt_time()
                        data, status = validate_completed_bars(frame, now)
                        status["feed_metadata"] = dict(frame.attrs)
                        status["source"] = frame.attrs.get("source", SOURCE)
                        status["live_feed_verified"] = bool(data is not None and frame.attrs.get("live_feed_verified"))
                        try:
                            market_open_at_receipt = futures_active(now)
                        except Exception as exc:
                            data, active = None, False
                            status.update(status="calendar_unavailable", error_type=type(exc).__name__)
                        else:
                            if not market_open_at_receipt:
                                data, active = None, False
                                status["status"] = "closed"
                    except Exception as exc:
                        now = receipt_time()
                        data = None
                        status = {"status": "provider_error", "error_type": type(exc).__name__,
                                  "last_completed_bar": previous.get("last_bar_end"),
                                  "data_status": getattr(exc, "reason", "provider_error")}
                    if data is None:
                        status["last_completed_bar"] = status.get("last_completed_bar") or previous.get("last_bar_end")
                        events.extend(self._cancel(symbol, now, status, status["status"]))
                        if status["status"] != "closed":
                            heartbeat["status"] = "calendar_unavailable" if status["status"] == "calendar_unavailable" else "degraded"
                        self._record({"record_type": "observation", "symbol": symbol,
                                      "bar_end": status["last_completed_bar"], "detected_at": now.isoformat(),
                                      "decision": "CLOSED" if status["status"] == "closed" else "REJECTED", "reason": status["status"],
                                      "analysis_only": True, "notify_eligible": False})
                    else:
                        self._resolve_outcomes(symbol, data, now)
                        last = previous.get("last_bar_end")
                        indexes = [len(data) - 1] if not last else [
                            i for i, start in enumerate(data.index)
                            if (start.to_pydatetime() + BAR).isoformat() > last
                            and now - (start.to_pydatetime() + BAR) <= MAX_AGE]
                        if indexes and last and data.index[indexes[0]].to_pydatetime() > datetime.fromisoformat(last):
                            # Never join nonconsecutive closes into confirmation or
                            # silently miss an intervening invalidation after sleep.
                            events.extend(self._cancel(symbol, now, status, "missed_polling_bars"))
                            status["recovery_status"] = "missed_polling_bars"
                            heartbeat["status"] = "degraded"
                            self._record({"record_type": "observation", "symbol": symbol,
                                          "bar_end": status["last_completed_bar"], "detected_at": now.isoformat(),
                                          "decision": "MISSED_BARS", "reason": "missed_polling_bars",
                                          "analysis_only": True, "notify_eligible": False})
                        for index in indexes:
                            try:
                                events.extend(self._process_bar(symbol, data, index, now))
                            except Exception as exc:
                                status.update(status="detector_error", error_type=type(exc).__name__)
                                heartbeat["status"] = "degraded"
                                events.extend(self._cancel(symbol, now, status, "detector_error"))
                                break
                heartbeat["symbols"][symbol] = status
            heartbeat["timestamp"] = receipt_time().isoformat()
            heartbeat["price_action_context"] = dict(self.price_context_status)
            self._save()
            self._record(heartbeat)
        except (OSError, ValueError, TypeError) as exc:
            self.persistence_error = "persistence_failed"
            heartbeat.update(status="persistence_failed", error_type=type(exc).__name__)
            # A nonpersistent decision is never eligible for an outbound alert.
        return {"events": events, "heartbeat": heartbeat}


class NotificationGate:
    """Optional at-most-once reservation; delivery cap applies ONLY after detection.

    Not used for experimental alerts. Reserve before sending because an HTTP
    timeout leaves delivery uncertain; suppress retry rather than duplicate it.
    """
    def __init__(self, runtime: HunterRuntime, max_daily=2, cooldown_seconds=7200):
        self.runtime = runtime
        self.max_daily = max(0, int(max_daily))
        self.cooldown_seconds = max(0, int(cooldown_seconds))

    def reserve(self, event, now):
        now = utc(now)
        if self.runtime.persistence_error or not event.get("notify_eligible", False):
            return False
        state = self.runtime.state["notifications"]
        today = now.astimezone(NY).date().isoformat()
        if state.get("day") != today:
            state.update(day=today, count=0)
        seen = state.setdefault("seen", [])
        group = f"{event['symbol']}:{event['direction']}"
        last = state.setdefault("last", {}).get(group)
        if event["event_id"] in seen or state.get("count", 0) >= self.max_daily:
            return False
        if last and (now - datetime.fromisoformat(last)).total_seconds() < self.cooldown_seconds:
            return False
        seen.append(event["event_id"])
        state["seen"] = seen[-2000:]
        state["last"][group] = now.isoformat()
        state["count"] = state.get("count", 0) + 1
        try:
            self.runtime._save()
        except OSError:
            self.runtime.persistence_error = "persistence_failed"
            return False
        return True


def format_research_event(event):
    """Concise Arabic evidence; probability and option execution stay unavailable."""
    price = "غير متاح" if event["price"] is None else f"{event['price']:.2f}"
    return (f"سهيل هنتر | {event['state_ar']} بحثي | {event['symbol']} | {event['direction']}\n"
            f"الأصل: {price} | المستوى: {event['level']:.2f} | الإلغاء: {event['invalidation']:.2f}\n"
            f"شمعة مكتملة: {event['bar_end']} | الرصد: {event['detected_at']}\n"
            f"المصدر: {event['source']} | الثقة: غير معايرة\n"
            "NOT READY — مراقبة الأصل فقط؛ لا أسعار عقود SPX ولا أوامر تداول.")

