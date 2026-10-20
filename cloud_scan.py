"""Best-effort scheduled entry point for the canonical Hunter shadow runtime.

No GitHub issues, Telegram messages, option suggestions or orders are emitted.
The journal and heartbeat are retained by the workflow even on a data outage.
"""
import argparse
import json
import os
from pathlib import Path

from globex_render_worker import create_runtime, run_once


def run(now=None, state_dir=None, fetcher=None, allow_stale_feed=False):
    runtime = create_runtime(state_dir)
    result = run_once(runtime, now, fetcher)
    heartbeat = result["heartbeat"]
    target = Path(runtime.state_path).parent / "heartbeat.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(heartbeat, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(heartbeat, ensure_ascii=False))
    summary = os.getenv("GITHUB_STEP_SUMMARY")
    if summary:
        with Path(summary).open("a", encoding="utf-8") as stream:
            stream.write("## Hunter shadow data health\n\n"
                         "Job completion is not live-feed verification or trading readiness.\n\n"
                         "```json\n" + json.dumps(heartbeat, ensure_ascii=False, indent=2)
                         + "\n```\n")
    if heartbeat["status"] == "ok":
        return 0
    # Only known Yahoo latency is nonfatal for scheduled research. Provider,
    # detector, calendar and persistence failures must still fail the job.
    states = [item["status"] for item in heartbeat.get("symbols", {}).values()]
    stale_only = (heartbeat["status"] == "degraded" and "stale_feed" in states
                  and all(state in {"ok", "closed", "stale_feed"} for state in states)
                  and not any(item.get("recovery_status") for item in heartbeat["symbols"].values()))
    if allow_stale_feed and stale_only:
        print("::warning title=Delayed market data::Yahoo bars were rejected as stale; "
              "Hunter remains NOT_READY. See heartbeat artifact and job summary.")
        return 0
    return 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-stale-feed", action="store_true",
                        help="record known feed latency as a warning; keep real errors fatal")
    return run(allow_stale_feed=parser.parse_args().allow_stale_feed)


if __name__ == "__main__":
    raise SystemExit(main())

