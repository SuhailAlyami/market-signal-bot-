"""Background IBKR market-data reader; explicit opt-out, no orders or alerts.

Missing independent OAuth state returns authorization_required without network
requests or implicit sign-in. Existing ChatGPT credentials are never exported.
"""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import threading
import time

from ibkr_mcp import SOURCE, report_health, save_report

_THREAD = None


def report_path():
    return Path(os.getenv("IBKR_MCP_REPORT", ".hunter-state/ibkr_snapshot.json"))


def get_status():
    if os.getenv("IBKR_MCP_ENABLED", "true").lower() != "true":
        return {"status": "disabled", "source": SOURCE, "readiness": "NOT_READY", "orders_enabled": False}
    return report_health(report_path())


def poll_once():
    from ibkr_mcp_client import run_collection
    from premium_archive import archive_history

    archived = 0

    def retain(identity, raw, received_at):
        nonlocal archived
        archived += archive_history(report_path().parent, identity, raw, received_at)

    async def collect():
        return await asyncio.wait_for(run_collection(authorize=False, history_sink=retain), timeout=90)

    try:
        report = asyncio.run(collect())
        from premium_radar import journal_observations
        events = journal_observations(report, report_path().parent)
        report["premium_events_recorded"] = len(events)
        report["premium_bar_versions_recorded"] = archived
        from premium_shadow_outcomes import reconcile
        report["premium_outcomes"] = reconcile(report_path().parent)
    except Exception as exc:
        report = {"status": "error", "readiness": "NOT_READY", "source": SOURCE,
                  "orders_enabled": False, "reason": "worker_collection_failed",
                  "error_type": type(exc).__name__, "observed_at": datetime.now(timezone.utc).isoformat()}
    save_report(report, report_path())
    return report


def start_worker():
    global _THREAD
    if os.getenv("IBKR_MCP_ENABLED", "true").lower() != "true":
        return None
    if _THREAD and _THREAD.is_alive():
        return _THREAD
    try:
        interval = max(60, int(os.getenv("IBKR_MCP_POLL_SECONDS", "60")))
    except ValueError:
        interval = 60

    def loop():
        waiter = threading.Event()
        while True:
            started = time.monotonic()
            try:
                poll_once()
            except Exception:
                # Failed report writes leave a stale/unavailable health state.
                # Never claim the previous observation is current.
                pass
            # Keep a start-to-start cadence. Waiting a full interval AFTER
            # collection silently added network duration to every cycle.
            # Overruns never overlap or trigger a burst of catch-up requests.
            waiter.wait(poll_delay(interval, time.monotonic()-started))

    _THREAD = threading.Thread(target=loop, name="ibkr-mcp-reader", daemon=True)
    _THREAD.start()
    return _THREAD


def poll_delay(interval, elapsed):
    return max(1., interval - max(0., elapsed))
