"""Opt-in background IBKR collector; no Telegram or order capabilities."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import threading

from ibkr_mcp import SOURCE, report_health, save_report

_THREAD = None


def report_path():
    return Path(os.getenv("IBKR_MCP_REPORT", ".hunter-state/ibkr_snapshot.json"))


def get_status():
    if os.getenv("IBKR_MCP_ENABLED", "false").lower() != "true":
        return {"status": "disabled", "source": SOURCE, "readiness": "NOT_READY", "orders_enabled": False}
    return report_health(report_path())


def poll_once():
    from ibkr_mcp_client import run_collection

    async def collect():
        return await asyncio.wait_for(run_collection(authorize=False), timeout=90)

    try:
        report = asyncio.run(collect())
        from premium_radar import journal_observations
        events = journal_observations(report, report_path().parent)
        report["premium_events_recorded"] = len(events)
    except Exception as exc:
        report = {"status": "error", "readiness": "NOT_READY", "source": SOURCE,
                  "orders_enabled": False, "reason": "worker_collection_failed",
                  "error_type": type(exc).__name__, "observed_at": datetime.now(timezone.utc).isoformat()}
    save_report(report, report_path())
    return report


def start_worker():
    global _THREAD
    if os.getenv("IBKR_MCP_ENABLED", "false").lower() != "true":
        return None
    if _THREAD and _THREAD.is_alive():
        return _THREAD
    try:
        interval = max(60, int(os.getenv("IBKR_MCP_POLL_SECONDS", "60")))
    except ValueError:
        interval = 60

    def loop():
        while True:
            try:
                poll_once()
            except Exception:
                # Failed report writes leave a stale/unavailable health state.
                # Never claim the previous observation is current.
                pass
            threading.Event().wait(interval)

    _THREAD = threading.Thread(target=loop, name="ibkr-mcp-reader", daemon=True)
    _THREAD.start()
    return _THREAD
