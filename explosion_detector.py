"""Conservative market-data based SPY/QQQ breakout watcher. Analysis only; no orders."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import ibkr_market_data as market_data

NY = ZoneInfo("America/New_York")
SYMBOLS = ("SPY", "QQQ")
MAX_BAR_AGE = timedelta(minutes=12)


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


def assess_bars(symbol: str, bars: pd.DataFrame, now: datetime | None = None) -> dict | None:
    """Emit only on a complete, recent 5-minute bar; never use unfinished candles."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or not isinstance(bars.index, pd.DatetimeIndex):
        return None
    if bars.index.tz is None or len(bars) < 32:
        return None
    data = bars.sort_index().copy()
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in data or data[col].isna().iloc[-32:].any():
            return None
    # Five-minute bar timestamps denote bar START. Exclude current/incomplete bar.
    cutoff = now - timedelta(minutes=5)
    data = data[data.index <= cutoff]
    if len(data) < 32:
        return None
    last_time = data.index[-1].to_pydatetime().astimezone(timezone.utc)
    bar_close_time = last_time + timedelta(minutes=5)
    if bar_close_time > now or now - bar_close_time > MAX_BAR_AGE:
        return None
    recent = data.iloc[-31:-1]
    bar = data.iloc[-1]
    close = float(bar["Close"])
    volume = float(bar["Volume"])
    if close <= 0 or volume <= 0 or float(recent["Volume"].mean()) <= 0:
        return None
    # Compare with recent *completed* bars, avoiding look-ahead.
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
    if direction is None or rvol < 2.0 or abs(momentum_pct) < 0.35:
        return None
    breakout = prior_high if direction == "BULLISH" else prior_low
    distance = abs(close - breakout)
    if distance < 0.1 * atr:
        return None
    # Transparent rule-based strength, NOT calibrated probability.
    score = min(100, round(
        40 + 15 * min(rvol / 2, 2) + 15 * min(abs(momentum_pct) / 0.5, 2)
        + 15 * min(distance / atr, 2)
    ))
    return {
        "symbol": symbol, "direction": direction, "price": close, "rvol": rvol,
        "momentum_pct": momentum_pct, "score": score, "atr": atr,
        "breakout": breakout, "invalidated_below_above": breakout,
        "bar_time": bar_close_time.isoformat(), "provider": "IBKR MCP",
    }


def fetch_and_assess(symbol: str, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    bars = market_data.Ticker(symbol).history(period="5d", interval="5m", auto_adjust=True)
    if bars.empty:
        return None
    return assess_bars(symbol, bars, now)


def format_alert(item: dict) -> str:
    trend = "صعود محتمل" if item["direction"] == "BULLISH" else "هبوط محتمل"
    return (
        f"🔎 Suhail Hunter — WATCH: {trend}\n"
        f"الأصل: {item['symbol']} | السعر: {item['price']:.2f}\n"
        f"القوة الفنية: {item['score']}/100 (ليست احتمال نجاح)\n"
        f"الحجم النسبي RVOL: {item['rvol']:.2f}x | الزخم: {item['momentum_pct']:+.2f}%\n"
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
    # Per-symbol key: the same completed candle cannot trigger again, even on rerun.
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
    for symbol in SYMBOLS:
        try:
            item = fetch_and_assess(symbol, now)
            if not item:
                print(f"{symbol}: no qualifying recent confirmed breakout")
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

