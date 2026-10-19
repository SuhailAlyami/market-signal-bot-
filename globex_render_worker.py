"""Render wrapper for the single 1m Hunter shadow runtime; experimental alerts OFF."""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
import threading
from datetime import datetime, timezone
from pathlib import Path

from hunter_runtime import HunterRuntime, SOURCE

LOG = logging.getLogger("suhail.globex")
_STATUS = {"status": "not_started", "alerts_enabled": False, "readiness": "NOT_READY", "symbols": {}}
_THREAD = None


def get_status(now=None):
    """JSON-safe snapshot for /health, including unavailable/stale market data."""
    snapshot = json.loads(json.dumps(_STATUS))
    if snapshot.get("timestamp"):
        now = now or datetime.now(timezone.utc)
        age = max(0., (now - datetime.fromisoformat(snapshot["timestamp"])).total_seconds())
        snapshot["heartbeat_age_seconds"] = age
        try:
            interval = max(60, int(os.getenv("HUNTER_CHECK_SECONDS", "60")))
        except ValueError:
            interval = 60
        if age > max(180, interval * 3):
            snapshot["last_status"] = snapshot["status"]
            snapshot["status"] = "worker_stalled"
    return snapshot


def yahoo_bars(symbol):
    import yfinance as yf

    return yf.Ticker(symbol).history(period="5d", interval="1m", auto_adjust=False, raise_errors=True)


def create_runtime(state_dir=None):
    directory = Path(state_dir or os.getenv("HUNTER_STATE_DIR", ".hunter-state"))
    return HunterRuntime(directory / "state.json", directory / "shadow.jsonl")


def run_once(runtime=None, now=None, fetcher=None):
    global _STATUS
    runtime = runtime or create_runtime()
    live_clock = (lambda: datetime.now(timezone.utc)) if now is None else None
    result = runtime.poll(now or datetime.now(timezone.utc), fetcher or yahoo_bars, clock=live_clock)
    _STATUS = result["heartbeat"]
    LOG.info("Hunter heartbeat %s", json.dumps(_STATUS, ensure_ascii=False))
    return result



def send_shadow_telegram(events, heartbeat, token=None, chat_id=None):
    """Send clearly labelled research observations, never option trade recommendations.

    Fail closed if the underlying feed is not fresh; dedupe is provided by
    HunterRuntime's persisted event transitions, not by the messaging API.
    """
    token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id or heartbeat.get("status") != "ok":
        return 0
    delivered = 0
    for event in events:
        if not event.get("notify_eligible", False):\n            continue\n        if event.get("state") not in ("SETUP", "TRIGGER"):
            continue
        if event.get("source") != SOURCE:
            continue
        delay = event.get("detection_delay_seconds")
        if delay is None or not (0 <= delay <= 90):
            continue
        direction = "صعود" if event["direction"] == "UP" else "هبوط"
        message = ("🔬 سهيل هنتر | رصد تجريبي وليس توصية شراء\n"
                   f"الحالة: {event['state']} | الأصل: {event['symbol']}\n"
                   f"الاتجاه المحتمل: {direction}\n"
                   f"السعر المرجعي: {event['price']}\n"
                   f"مستوى الإلغاء: {event['invalidation']}\n"
                   f"وقت الشمعة UTC: {event['bar_end']}\n"
                   f"تأخر الرصد: {delay:.0f} ثانية\n"
                   "لا توجد بيانات أسعار عقود SPX أو سترايك أو دخول موثوق.")
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode()
        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=payload),
                timeout=8,
            ) as response:
                if response.status == 200:
                    delivered += 1
        except Exception as exc:
            LOG.warning("Hunter Telegram delivery failed: %s", type(exc).__name__)
    return delivered

def start_worker(token=None, chat_id=None):
    """Keep bootstrap compatibility; Telegram credentials never gate detection."""
    global _THREAD
    if _THREAD and _THREAD.is_alive():
        return _THREAD
    try:
        interval = max(60, int(os.getenv("HUNTER_CHECK_SECONDS", "60")))
    except ValueError:
        interval = 60
    runtime = create_runtime()
    stop = threading.Event()
    LOG.warning("Hunter NOT READY: Telegram research observations gated by freshness; no SPX option recommendations")

    def loop():
        global _STATUS
        while not stop.is_set():
            try:
                result = run_once(runtime)
                send_shadow_telegram(result['events'], result['heartbeat'], token, chat_id)
            except Exception as exc:
                _STATUS = {"status": "worker_error", "error_type": type(exc).__name__,
                           "timestamp": datetime.now(timezone.utc).isoformat(),
                           "alerts_enabled": False, "readiness": "NOT_READY"}
                LOG.warning("Hunter worker error: %s", type(exc).__name__)
            stop.wait(interval)

    _THREAD = threading.Thread(target=loop, daemon=True, name="hunter-shadow")
    _THREAD.start()
    return _THREAD


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Single underlying shadow observation, no notifications")
    parser.add_argument("--once", action="store_true", help="run a single observation (default)")
    parser.add_argument("--state-dir", default=None)
    args = parser.parse_args()
    result = run_once(create_runtime(args.state_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["heartbeat"]["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
