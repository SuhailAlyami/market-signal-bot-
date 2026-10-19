"""Best-effort scheduled entry point for the canonical Hunter shadow runtime.

No GitHub issues, Telegram messages, option suggestions or orders are emitted.
The journal and heartbeat are retained by the workflow even on a data outage.
"""
import json
from pathlib import Path

from globex_render_worker import create_runtime, run_once


def run(now=None, state_dir=None, fetcher=None):
    runtime = create_runtime(state_dir)
    result = run_once(runtime, now, fetcher)
    heartbeat = result["heartbeat"]
    target = Path(runtime.state_path).parent / "heartbeat.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(heartbeat, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(heartbeat, ensure_ascii=False))
    return 0 if heartbeat["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(run())
