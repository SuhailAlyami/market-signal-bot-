"""NYSE-session research alerts through the existing Render Telegram configuration.

No option contract suggestions. Yahoo Finance bars can be delayed or missing.
"""
from __future__ import annotations
import logging
import threading
import time
from datetime import datetime, timezone

import requests

from explosion_detector import fetch_and_assess, format_alert, market_session_open

LOG = logging.getLogger("suhail.us_watch")
SYMBOLS = ("SPY", "QQQ")


def start_worker(token: str, chat_id: str, poll_seconds: int = 300) -> None:
    if not token or not chat_id:
        LOG.warning("US watcher disabled: Telegram configuration unavailable")
        return

    def run():
        sent = set()
        while True:
            try:
                now = datetime.now(timezone.utc)
                if market_session_open(now):
                    for symbol in SYMBOLS:
                        try:
                            result = fetch_and_assess(symbol, now)
                            if result is None:
                                continue
                            key = (result["symbol"], result["direction"], result["bar_time"])
                            if key in sent:
                                continue
                            response = requests.post(
                                f"https://api.telegram.org/bot{token}/sendMessage",
                                json={"chat_id": chat_id, "text": format_alert(result)},
                                timeout=15,
                            )
                            response.raise_for_status()
                            sent.add(key)
                            LOG.info("US WATCH alert Telegram accepted for %s", symbol)
                        except Exception as exc:
                            LOG.warning("US WATCH skipped %s (%s)", symbol, type(exc).__name__)
                else:
                    LOG.debug("NYSE closed: US watcher sleeping")
            except Exception as exc:
                LOG.warning("US watch iteration error: %s", type(exc).__name__)
            time.sleep(poll_seconds)

    threading.Thread(target=run, daemon=True, name="nyse-watch").start()
