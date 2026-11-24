"""SPY/QQQ breakout watch. Analysis only; no orders.

The alert path defaults to the original completed-bar confirmation (30-bar
range, relative volume, and a five-bar move). An early ATR range-release mode
is available for research (`EXPLOSION_MODE=early`) and was not promoted: on the
held-out Yahoo sessions it caught far fewer explosions and did not improve
entry quality. Thresholds for both modes are ExplosionConfig fields and
EXPLOSION_* environment variables.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import ibkr_market_data as market_data

NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "QQQ")
MAX_BAR_AGE = timedelta(minutes=12)
BAR_MINUTES = 5


@dataclass(frozen=True)
class ExplosionConfig:
    """Tunable gates. Distances are in prior-ATR units, not fixed percentages.

    ext_min_atr / ext_max_atr bound how far the signal close may sit beyond the
    prior short-range extreme. The upper bound is the early-entry guard: a close
    that has already run further than this is treated as late and is not alerted.
    """

    mode: str = "legacy"
    lookback: int = 8
    atr_period: int = 14
    volume_baseline: int = 20
    rvol_min: float = 1.8
    ext_min_atr: float = 0.05
    ext_max_atr: float = 0.45
    body_min_atr: float = 0.15
    cooldown_bars: int = 6
    min_score: float = 0.0
    legacy_lookback: int = 30
    legacy_rvol_min: float = 2.0
    legacy_momentum_pct: float = 0.35
    legacy_min_distance_atr: float = 0.1
    max_bar_age: timedelta = MAX_BAR_AGE
    bar_minutes: int = BAR_MINUTES

    def validate(self) -> "ExplosionConfig":
        if self.mode not in ("legacy", "early"):
            raise ValueError("mode must be legacy or early")
        if self.legacy_lookback < 5 or self.legacy_rvol_min <= 0 or self.legacy_momentum_pct < 0:
            raise ValueError("invalid legacy threshold")
        if self.legacy_min_distance_atr < 0:
            raise ValueError("invalid legacy distance")
        if self.lookback < 2 or self.atr_period < 2 or self.volume_baseline < 2:
            raise ValueError("lookback, atr_period and volume_baseline must be >= 2")
        if not 0 <= self.ext_min_atr < self.ext_max_atr:
            raise ValueError("require 0 <= ext_min_atr < ext_max_atr")
        if self.rvol_min <= 0 or self.body_min_atr < 0 or self.cooldown_bars < 1:
            raise ValueError("invalid rvol, body or cooldown")
        if self.min_score < 0 or self.min_score > 100:
            raise ValueError("min_score must be inside 0..100")
        if self.bar_minutes < 1 or self.max_bar_age <= timedelta(0):
            raise ValueError("invalid bar size or freshness window")
        return self


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def config_from_env(base: ExplosionConfig | None = None) -> ExplosionConfig:
    """Overlay EXPLOSION_* variables on the dataclass defaults."""
    cfg = base or ExplosionConfig()
    age_min = _env_float("EXPLOSION_MAX_BAR_AGE_MIN", cfg.max_bar_age.total_seconds() / 60.0)
    mode = os.getenv("EXPLOSION_MODE", cfg.mode).strip().lower() or cfg.mode
    return replace(
        cfg,
        mode=mode,
        lookback=_env_int("EXPLOSION_LOOKBACK", cfg.lookback),
        legacy_lookback=_env_int("EXPLOSION_LEGACY_LOOKBACK", cfg.legacy_lookback),
        legacy_rvol_min=_env_float("EXPLOSION_LEGACY_RVOL_MIN", cfg.legacy_rvol_min),
        legacy_momentum_pct=_env_float("EXPLOSION_LEGACY_MOMENTUM_PCT", cfg.legacy_momentum_pct),
        legacy_min_distance_atr=_env_float("EXPLOSION_LEGACY_MIN_DISTANCE_ATR", cfg.legacy_min_distance_atr),
        atr_period=_env_int("EXPLOSION_ATR_PERIOD", cfg.atr_period),
        volume_baseline=_env_int("EXPLOSION_VOLUME_BASELINE", cfg.volume_baseline),
        rvol_min=_env_float("EXPLOSION_RVOL_MIN", cfg.rvol_min),
        ext_min_atr=_env_float("EXPLOSION_EXT_MIN_ATR", cfg.ext_min_atr),
        ext_max_atr=_env_float("EXPLOSION_EXT_MAX_ATR", cfg.ext_max_atr),
        body_min_atr=_env_float("EXPLOSION_BODY_MIN_ATR", cfg.body_min_atr),
        cooldown_bars=_env_int("EXPLOSION_COOLDOWN_BARS", cfg.cooldown_bars),
        min_score=_env_float("EXPLOSION_MIN_SCORE", cfg.min_score),
        max_bar_age=timedelta(minutes=age_min),
    ).validate()


def watched_symbols() -> tuple[str, ...]:
    raw = os.getenv("EXPLOSION_SYMBOLS", ",".join(SYMBOLS))
    symbols = tuple(part.strip() for part in raw.split(",") if part.strip())
    return symbols or SYMBOLS


def minimum_bars(cfg: ExplosionConfig) -> int:
    return max(cfg.lookback, cfg.atr_period, cfg.volume_baseline) + 2


def market_session_open(now: datetime | None = None) -> bool:
    """Uses the NYSE calendar, including holidays and early closes."""
    import pandas_market_calendars as mcal

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone aware")
    cal = mcal.get_calendar("NYSE")
    local = now.astimezone(NY)
    schedule = cal.schedule(start_date=local.date(), end_date=local.date())
    if schedule.empty:
        return False
    session = schedule.iloc[0]
    return session["market_open"].to_pydatetime() <= now <= session["market_close"].to_pydatetime()


def _true_range(data: pd.DataFrame) -> pd.Series:
    previous = data["Close"].shift()
    return pd.concat([
        data["High"] - data["Low"],
        (data["High"] - previous).abs(),
        (data["Low"] - previous).abs(),
    ], axis=1).max(axis=1)


def prepare_completed(bars: pd.DataFrame, now: datetime | None, cfg: ExplosionConfig) -> pd.DataFrame | None:
    """Return sorted completed bars, or None when the frame is unusable or stale."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not isinstance(bars.index, pd.DatetimeIndex):
        return None
    if bars.index.tz is None:
        return None
    need = minimum_bars(cfg)
    if len(bars) < need:
        return None
    data = bars.sort_index()
    if not data.index.is_unique:
        return None
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in data:
            return None
    cutoff = now - timedelta(minutes=cfg.bar_minutes)
    data = data.loc[data.index <= cutoff]
    if len(data) < need:
        return None
    tail = data.iloc[-need:]
    if tail[["Open", "High", "Low", "Close", "Volume"]].isna().any().any():
        return None
    last_time = data.index[-1].to_pydatetime().astimezone(timezone.utc)
    bar_close_time = last_time + timedelta(minutes=cfg.bar_minutes)
    if bar_close_time > now or now - bar_close_time > cfg.max_bar_age:
        return None
    row = data.iloc[-1]
    close = float(row["Close"])
    volume = float(row["Volume"])
    high = float(row["High"])
    low = float(row["Low"])
    open_ = float(row["Open"])
    if close <= 0 or volume <= 0 or high < max(open_, close, low) or low > min(open_, close):
        return None
    return data


def _window_is_contiguous(index: pd.DatetimeIndex, bar_minutes: int) -> bool:
    if len(index) < 2:
        return False
    deltas = index.to_series().diff().iloc[1:]
    return bool((deltas <= pd.Timedelta(minutes=bar_minutes + 2)).all())


def raw_signal(completed: pd.DataFrame, symbol: str, cfg: ExplosionConfig) -> dict | None:
    """Decide from the last completed bar only. Caller enforces freshness and cooldown."""
    cfg.validate()
    need = minimum_bars(cfg)
    if len(completed) < need:
        return None
    window = completed.iloc[-(cfg.lookback + 1):]
    if not _window_is_contiguous(window.index, cfg.bar_minutes):
        return None
    ranges = _true_range(completed)
    atr = float(ranges.iloc[-(cfg.atr_period + 1):-1].mean())
    if not pd.notna(atr) or atr <= 0:
        return None
    baseline = completed["Volume"].iloc[-(cfg.volume_baseline + 1):-1]
    if float((baseline > 0).mean()) < 0.8:
        return None
    base_volume = float(baseline.mean())
    bar = completed.iloc[-1]
    volume = float(bar["Volume"])
    if base_volume <= 0 or volume <= 0:
        return None
    prior = completed.iloc[-(cfg.lookback + 1):-1]
    prior_high = float(prior["High"].max())
    prior_low = float(prior["Low"].min())
    close = float(bar["Close"])
    open_ = float(bar["Open"])
    rvol = volume / base_volume
    previous_close = float(completed["Close"].iloc[-2])
    momentum_pct = 100.0 * (close / previous_close - 1.0)
    previous_body = float(completed["Close"].iloc[-2] - completed["Open"].iloc[-2]) / atr
    bull_ext = (close - prior_high) / atr
    bear_ext = (prior_low - close) / atr
    bull_body = (close - open_) / atr
    bear_body = (open_ - close) / atr

    def _candidate(direction: str, extension: float, body: float, level: float) -> dict | None:
        if not cfg.ext_min_atr <= extension <= cfg.ext_max_atr:
            return None
        if rvol < cfg.rvol_min or body < cfg.body_min_atr:
            return None
        room = (cfg.ext_max_atr - extension) / cfg.ext_max_atr
        accel = 1.0 if body > previous_body else 0.0
        if direction == "BEARISH":
            accel = 1.0 if body > -previous_body else 0.0
        score = min(100, round(
            25 * min(rvol / 3.0, 1.0)
            + 35 * max(0.0, room)
            + 25 * min(body / 1.0, 1.0)
            + 15 * accel
        ))
        if score < cfg.min_score:
            return None
        bar_close = completed.index[-1].to_pydatetime().astimezone(timezone.utc) + timedelta(minutes=cfg.bar_minutes)
        return {
            "symbol": symbol,
            "direction": direction,
            "price": close,
            "rvol": rvol,
            "momentum_pct": momentum_pct,
            "score": score,
            "atr": atr,
            "breakout": level,
            "invalidated_below_above": level,
            "bar_time": bar_close.isoformat(),
            "provider": "IBKR MCP",
            "state": "SETUP",
            "state_ar": "استعداد",
            "reason": "early_range_release",
            "extension_atr": extension,
            "body_atr": body,
            "lookback": cfg.lookback,
            "confidence_status": "uncalibrated",
        }

    bull = _candidate("BULLISH", bull_ext, bull_body, prior_high)
    bear = _candidate("BEARISH", bear_ext, bear_body, prior_low)
    if bull and bear:
        return None
    return bull or bear


def regular_hours_start(ts: datetime | pd.Timestamp) -> bool:
    """True when a bar START is inside 09:30–16:00 America/New_York.

    This clock filter does not know holidays; live sending still uses the NYSE calendar.
    """
    stamp = pd.Timestamp(ts)
    if stamp.tzinfo is None:
        return False
    local = stamp.tz_convert(NY)
    minutes = local.hour * 60 + local.minute
    return 9 * 60 + 30 <= minutes < 16 * 60


def _emitted_signal(signal: dict, bar_minutes: int) -> bool:
    close = datetime.fromisoformat(signal["bar_time"])
    start = close - timedelta(minutes=bar_minutes)
    return regular_hours_start(start)


def _assess_early(
    symbol: str,
    bars: pd.DataFrame,
    now: datetime | None = None,
    config: ExplosionConfig | None = None,
) -> dict | None:
    """Early entry on the latest completed regular-hours bar, with a causal cooldown.

    Cooldown only counts signals that would themselves have been emitted. An
    unsent premarket candidate must not block the first regular-session alert.
    """
    cfg = config if config is not None else config_from_env()
    completed = prepare_completed(bars, now, cfg)
    if completed is None:
        return None
    signal = raw_signal(completed, symbol, cfg)
    if signal is None or not _emitted_signal(signal, cfg.bar_minutes):
        return None
    for back in range(1, cfg.cooldown_bars):
        end = len(completed) - back
        if end < minimum_bars(cfg):
            break
        earlier = raw_signal(completed.iloc[:end], symbol, cfg)
        if earlier is None or earlier["direction"] != signal["direction"]:
            continue
        if _emitted_signal(earlier, cfg.bar_minutes):
            return None
    return signal


def assess_bars(
    symbol: str,
    bars: pd.DataFrame,
    now: datetime | None = None,
    config: ExplosionConfig | None = None,
) -> dict | None:
    """Alert decision. Legacy confirmation unless config or EXPLOSION_MODE selects early."""
    cfg = config if config is not None else config_from_env()
    if cfg.mode == "early":
        return _assess_early(symbol, bars, now, cfg)
    return assess_bars_legacy(symbol, bars, now, cfg)


def assess_bars_legacy(
    symbol: str,
    bars: pd.DataFrame,
    now: datetime | None = None,
    config: ExplosionConfig | None = None,
) -> dict | None:
    """Confirmation: prior-range break, relative volume, and a five-bar move.

    Defaults match the original rule (30 bars, RVOL>=2, move>=0.35%, distance>=0.1 ATR).
    """
    cfg = config or ExplosionConfig()
    need = max(cfg.legacy_lookback + 2, 16)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not isinstance(bars.index, pd.DatetimeIndex):
        return None
    if bars.index.tz is None or len(bars) < need:
        return None
    data = bars.sort_index().copy()
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in data or data[col].isna().iloc[-need:].any():
            return None
    cutoff = now - timedelta(minutes=cfg.bar_minutes)
    data = data[data.index <= cutoff]
    if len(data) < need:
        return None
    last_time = data.index[-1].to_pydatetime().astimezone(timezone.utc)
    bar_close_time = last_time + timedelta(minutes=cfg.bar_minutes)
    if bar_close_time > now or now - bar_close_time > cfg.max_bar_age:
        return None
    recent = data.iloc[-(cfg.legacy_lookback + 1):-1]
    bar = data.iloc[-1]
    close = float(bar["Close"])
    volume = float(bar["Volume"])
    if close <= 0 or volume <= 0 or float(recent["Volume"].mean()) <= 0:
        return None
    rvol = volume / float(recent["Volume"].mean())
    prior_high = float(recent["High"].max())
    prior_low = float(recent["Low"].min())
    price_5_bars_ago = float(data["Close"].iloc[-6])
    momentum_pct = 100.0 * (close / price_5_bars_ago - 1)
    ranges = pd.concat([
        data["High"] - data["Low"],
        (data["High"] - data["Close"].shift()).abs(),
        (data["Low"] - data["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    atr = float(ranges.iloc[-15:-1].mean())
    if atr <= 0:
        return None
    direction = "BULLISH" if close > prior_high and momentum_pct > 0 else (
        "BEARISH" if close < prior_low and momentum_pct < 0 else None
    )
    if direction is None or rvol < cfg.legacy_rvol_min or abs(momentum_pct) < cfg.legacy_momentum_pct:
        return None
    breakout = prior_high if direction == "BULLISH" else prior_low
    distance = abs(close - breakout)
    if distance < cfg.legacy_min_distance_atr * atr:
        return None
    score = min(100, round(
        40 + 15 * min(rvol / 2, 2) + 15 * min(abs(momentum_pct) / 0.5, 2)
        + 15 * min(distance / atr, 2)
    ))
    return {
        "symbol": symbol, "direction": direction, "price": close, "rvol": rvol,
        "momentum_pct": momentum_pct, "score": score, "atr": atr,
        "breakout": breakout, "invalidated_below_above": breakout,
        "bar_time": bar_close_time.isoformat(), "provider": "IBKR MCP",
        "state": "TRIGGER", "state_ar": "دخول مشروط", "reason": "legacy_30bar_confirmation",
        "confidence_status": "uncalibrated",
    }


def fetch_and_assess(symbol: str, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    bars = market_data.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True)
    if bars.empty:
        return None
    return assess_bars(symbol, bars, now)


def format_alert(item: dict) -> str:
    trend = "صعود محتمل" if item["direction"] == "BULLISH" else "هبوط محتمل"
    state = item.get("state_ar", "استعداد")
    extension = item.get("extension_atr")
    extension_line = ""
    if extension is not None:
        extension_line = f"بُعد الإغلاق عن المستوى: {extension:.2f} ATR (دخول مبكر، ليس بعد اكتمال الحركة)\n"
    return (
        f"🔎 Suhail Hunter — WATCH: {trend}\n"
        f"الحالة: {state}\n"
        f"الأصل: {item['symbol']} | السعر: {item['price']:.2f}\n"
        f"القوة الفنية: {item['score']}/100 (ليست احتمال نجاح)\n"
        f"الحجم النسبي RVOL: {item['rvol']:.2f}x | حركة شمعة الإشارة: {item['momentum_pct']:+.2f}%\n"
        f"{extension_line}"
        f"مستوى الاختراق/الكسر: {item['breakout']:.2f}\n"
        f"إلغاء السيناريو عند العودة عبر المستوى المذكور\n"
        f"شمعة مكتملة: {item['bar_time']}\n"
        f"المصدر: {item['provider']}\n"
        f"رصد فني فقط؛ ليست توصية عقد 0DTE أو أمر تداول."
    )


def reserve_once(item: dict) -> bool:
    """Reserve this candle in a private GitHub issue before sending; fail closed.

    Not exactly-once Telegram delivery: a failure after reservation may suppress an alert.
    The reservation is preferred to repeated trade-like notifications.
    """
    token = os.getenv("GITHUB_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY")
    if not token or not repository:
        print("Deduplication unavailable: no alerts will be sent")
        return False
    url = f"https://api.github.com/repos/{repository}/issues"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    title = f"[Suhail Hunter State] {item['symbol']}"
    key = f"{item['symbol']}:{item['direction']}:{item['bar_time']}"
    try:
        resp = requests.get(url, headers=headers, params={"state": "all", "per_page": 100}, timeout=15)
        resp.raise_for_status()
        matching = [issue for issue in resp.json() if issue.get("title") == title and "pull_request" not in issue]
        if matching:
            issue = matching[0]
            if issue.get("body", "").strip() == key:
                return False
            resp = requests.patch(issue["url"], headers=headers, json={"body": key}, timeout=15)
        else:
            resp = requests.post(url, headers=headers, json={
                "title": title, "body": key,
            }, timeout=15)
        resp.raise_for_status()
        return True
    except (requests.RequestException, ValueError, KeyError, TypeError):
        print("Deduplication API error: alert suppressed")
        return False


def run() -> int:
    if os.getenv("EXPLOSION_MODE", "legacy").strip().lower() == "context":
        from research_1m_lead import context_mode_status
        print(context_mode_status())
        return 0
    now = datetime.now(timezone.utc)
    if not market_session_open(now):
        print("NYSE closed: no alerts")
        return 0
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Missing Telegram credentials: alerts disabled")
        return 1
    sent = 0
    for symbol in watched_symbols():
        try:
            item = fetch_and_assess(symbol, now)
            if not item:
                print(f"{symbol}: no qualifying early range release")
                continue
            if not reserve_once(item):
                print(f"{symbol}: duplicate or deduplication unavailable; alert suppressed")
                continue
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": format_alert(item)},
                timeout=15,
            )
            resp.raise_for_status()
            sent += 1
            print(f"Sent {symbol} signal for completed bar {item['bar_time']}")
        except Exception as exc:
            print(f"{symbol}: failed ({type(exc).__name__}); credentials not logged")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
