"""Early Asia Globex futures proxy watch. Research alerts only, no trade orders."""
from __future__ import annotations
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone, time as clock_time
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

LOG = logging.getLogger("suhail.asia")
UTC = timezone.utc
FUTURES = ("ES=F", "NQ=F")
CHECK_SECONDS = 900

def futures_session_start(now):
    """Globex ES/NQ open: 18:00 US Eastern before each Tokyo business day.

    Sunday US evening corresponds to Monday morning in Tokyo. The precise
    UTC time changes with US DST. Holiday gaps are filtered by bar validation.
    """
    tokyo = now.astimezone(ZoneInfo("Asia/Tokyo"))
    if tokyo.weekday() >= 5:
        return None
    previous_us_date = tokyo.date() - timedelta(days=1)
    return datetime.combine(previous_us_date, clock_time(18, 0),
                            tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)


def asia_session(now):
    """From Globex US evening reopen to 15:00 Tokyo, Mon-Fri local."""
    tokyo = now.astimezone(ZoneInfo("Asia/Tokyo"))
    start = futures_session_start(now)
    return start is not None and start <= now.astimezone(UTC) and tokyo.hour < 15

def detect(symbol, frame, now):
    """Use complete 15-minute bars only. Return a WATCH if Asia opening range breaks."""
    if not asia_session(now) or not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        return None
    if any(col not in frame for col in ("High", "Low", "Close", "Volume")):
        return None
    data = frame.sort_index()
    # Yahoo Finance bars are labeled with START timestamp.
    data = data[data.index <= pd.Timestamp(now - timedelta(minutes=15))]
    if len(data) < 14:
        return None
    last = data.iloc[-1]
    end = data.index[-1].to_pydatetime().astimezone(UTC) + timedelta(minutes=15)
    if now - end > timedelta(minutes=35) or end > now:
        return None
    # First four fully completed 15-minute candles after the Globex reopen.
    start = futures_session_start(now)
    if start is None:
        return None
    idx_utc = data.index.tz_convert(UTC)
    opening = data[(idx_utc >= pd.Timestamp(start))
                   & (idx_utc < pd.Timestamp(start + timedelta(hours=1)))]
    if len(opening) != 4:
        return None
    if end < start + timedelta(hours=1):
        return None
    high, low = float(opening.High.max()), float(opening.Low.min())
    close, vol = float(last.Close), float(last.Volume)
    historical = data.iloc[-13:-1]
    if historical.Volume.isna().any() or pd.isna(close) or vol <= 0:
        return None
    avg = float(historical.Volume.mean())
    if avg <= 0:
        return None
    rv = vol / avg
    direction = "WATCH_DOWN" if close < low else ("WATCH_UP" if close > high else None)
    if not direction or rv < 1.5:
        return None
    return dict(symbol=symbol, direction=direction, price=close, rvol=rv,
                top=high, bottom=low, bar_end=end.isoformat(),
                session_date=str(day), source="Yahoo Finance futures proxy, may be delayed")

def scan_once(now=None):
    now = now or datetime.now(UTC)
    if not asia_session(now):
        return []
    found=[]
    for symbol in FUTURES:
        try:
            frame=yf.Ticker(symbol).history(period="5d",interval="15m",auto_adjust=True)
            if not frame.empty:
                alert=detect(symbol,frame,now)
                if alert:
                    found.append(alert)
        except Exception as exc:
            LOG.warning("Asia data unavailable for %s: %s",symbol,type(exc).__name__)
    return found

def start_worker(token, chat_id):
    """Daemon polls every 15m, not continuously. Live signal reliability is not guaranteed."""
    if not token or not chat_id:
        LOG.warning("Asia watcher disabled: Telegram env variables unavailable")
        return
    def loop():
        sent=set()
        while True:
            try:
                now=datetime.now(UTC)
                if asia_session(now):
                    for item in scan_once(now):
                        # In-process deduplication; resets if Render restarts.
                        key=(item["session_date"],item["symbol"],item["direction"])
                        if key in sent:
                            continue
                        trend="هبوط محتمل" if item["direction"]=="WATCH_DOWN" else "صعود محتمل"
                        message=(
                            f"🌏 سهيل هنتر | مراقبة آسيا: {trend}\\n"
                            f"عقود المؤشر المستقبلية: {item['symbol']} — {item['price']:.2f}\\n"
                            f"نطاق الساعة الأولى: {item['bottom']:.2f}–{item['top']:.2f}\\n"
                            f"الحجم النسبي: {item['rvol']:.2f}x\\n"
                            f"آخر شمعة مكتملة: {item['bar_end']}\\n"
                            "المصدر Yahoo Finance وقد يتأخر. ليست توصية SPX 0DTE؛ "
                            "حركة آسيا لا تضمن اتجاه نيويورك."
                        )
                        response=requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id":chat_id,"text":message},timeout=15)
                        response.raise_for_status()
                        sent.add(key)
                        LOG.info("Asia WATCH Telegram accepted: %s %s",item["symbol"],item["direction"])
            except Exception as exc:
                LOG.error("Asia watch error: %s",type(exc).__name__)
            time.sleep(CHECK_SECONDS)
    threading.Thread(target=loop,daemon=True,name="asia-monitor").start()
