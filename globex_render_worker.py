"""Low-noise ES/NQ Globex research alerts using existing Render Telegram credentials."""
import logging
import os
import threading
import time
from datetime import datetime, timezone

import requests
from early_globex_watch import globex_active, scan_once

LOG = logging.getLogger("suhail.globex")


def start_worker(token, chat_id):
    if not token or not chat_id:
        LOG.warning("Globex watcher disabled: Telegram credentials unavailable")
        return
    interval = max(300, int(os.getenv("GLOBEX_CHECK_SECONDS", "300")))
    cooldown = max(1800, int(os.getenv("GLOBEX_ALERT_COOLDOWN_SECONDS", "7200")))
    max_daily = max(1, int(os.getenv("GLOBEX_MAX_DAILY_ALERTS", "2")))

    def loop():
        sent = set()
        last_alert = {}
        day = None
        count = 0
        while True:
            try:
                now = datetime.now(timezone.utc)
                today = now.date()
                if today != day:
                    day, count = today, 0
                    sent.clear()
                if globex_active(now) and count < max_daily:
                    for item in scan_once(now):
                        key = (item["symbol"], item["direction"], item["bar_end"])
                        group = (item["symbol"], item["direction"])
                        if key in sent or now.timestamp() - last_alert.get(group, 0) < cooldown:
                            continue
                        if count >= max_daily:
                            break
                        direction = "صعود" if item["direction"] == "WATCH_UP" else "هبوط"
                        level = item["top"] if direction == "صعود" else item["bottom"]
                        invalidation = item["bottom"] if direction == "صعود" else item["top"]
                        message = (
                            f"🚨 سهيل هنتر | انفجار محتمل {direction} | {item['symbol']}\\n"
                            f"السعر: {item['price']:.2f} | الحجم النسبي: {item['rvol']:.2f}x\\n"
                            f"مستوى الكسر: {level:.2f} | الإلغاء: {invalidation:.2f}\\n"
                            f"شمعة مكتملة: {item['bar_end']}\\n"
                            "مراقبة بحثية فقط، بيانات Yahoo قد تتأخر. ليست توصية عقد SPX."
                        )
                        response = requests.post(
                            f"https://api.telegram.org/bot{token}/sendMessage",
                            json={"chat_id": chat_id, "text": message},
                            timeout=15,
                        )
                        response.raise_for_status()
                        sent.add(key)
                        last_alert[group] = now.timestamp()
                        count += 1
                        LOG.info("Globex alert delivered: %s %s", item["symbol"], item["direction"])
            except Exception as exc:
                LOG.warning("Globex watcher error: %s", type(exc).__name__)
            time.sleep(interval)

    threading.Thread(target=loop, daemon=True, name="globex-monitor").start()
