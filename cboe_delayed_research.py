"""Free Cboe *delayed* SPX option chain, for research only.

Do not use as a real-time feed, 0DTE entry price, or order signal.
Public endpoint may change or rate-limit requests. One request per invocation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/SPX.json"


def fetch_delayed_chain(*, timeout: float = 12) -> dict:
    request = Request(URL, headers={"User-Agent": "SuhailHunter-Research/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, ValueError, TimeoutError) as exc:
        return {"status": "NOT_READY", "reason": type(exc).__name__,
                "feed": "CBOE_DELAYED", "live_verified": False}
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return {"status": "NOT_READY", "reason": "unexpected_schema",
                "feed": "CBOE_DELAYED", "live_verified": False}
    data = payload["data"]
    options = data.get("options")
    if not isinstance(options, list):
        return {"status": "NOT_READY", "reason": "missing_options",
                "feed": "CBOE_DELAYED", "live_verified": False}
    return {
        "status": "DELAYED_RESEARCH_ONLY",
        "feed": "CBOE_DELAYED",
        "live_verified": False,
        "suitable_for_0dte_entry": False,
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider_timestamp": data.get("timestamp"),
        "options_count": len(options),
        "sample_contracts": [
            {"option": item.get("option"), "bid": item.get("bid"), "ask": item.get("ask"),
             "volume": item.get("volume"), "open_interest": item.get("open_interest")}
            for item in options[:3] if isinstance(item, dict)
        ],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args()
    print(json.dumps(fetch_delayed_chain(timeout=args.timeout), ensure_ascii=False))
