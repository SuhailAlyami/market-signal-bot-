"""GitHub Actions cloud scanner: stores read-only watch signals in GitHub Issues.

No Telegram credentials, Render service or trade execution required.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from urllib.parse import quote

import requests

from asia_watch import asia_session, scan_once
from explosion_detector import market_session_open, fetch_and_assess

REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
TIMEOUT = 20


def event_id(item: dict, kind: str) -> str:
    return f"{kind}:{item['symbol']}:{item['direction']}:{item.get('bar_end', item.get('bar_time'))}"


def issue_payload(item: dict, kind: str, now: datetime):
    direction = item["direction"]
    symbol = item["symbol"]
    bar = item.get("bar_end", item.get("bar_time"))
    identifier = event_id(item, kind)
    title = f"[Suhail WATCH] {kind} {symbol} {direction} {bar}"
    fields = {
        "kind": kind,
        "symbol": symbol,
        "direction": direction,
        "bar_time_utc": bar,
        "price": item["price"],
        "signal_id": identifier,
        "recorded_at_utc": now.isoformat(),
        "provider": item.get("source", item.get("provider", "Yahoo Finance (may be delayed)")),
        "analysis_only": True,
        "live_feed_verified": False,
    }
    if kind == "ASIA":
        fields.update(opening_high=item["top"], opening_low=item["bottom"], rvol=item["rvol"])
    else:
        fields.update(rvol=item["rvol"], momentum_pct=item["momentum_pct"],
                      technical_score=item["score"], breakout=item["breakout"])
    body = (
        "## Suhail Hunter — research WATCH, not a trade recommendation\n\n"
        "Not verified live exchange data. This is not an options quote or a predicted success rate.\n\n"
        "```json\n" + json.dumps(fields, ensure_ascii=False, indent=2) + "\n```\n"
    )
    return title, body


def publish_issue(item: dict, kind: str, now: datetime, session: requests.Session):
    """Fail closed if the remote dedupe check fails. No duplicates on reruns."""
    if not REPO or not TOKEN:
        raise RuntimeError("GitHub repo credentials are not set")
    title, body = issue_payload(item, kind, now)
    base = f"https://api.github.com/repos/{REPO}/issues"
    headers = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    # Dedupe exact key using issue search, which includes closed issues.
    # GitHub Search indexing can lag; Actions concurrency prevents overlapping runs.
    params = {"q": f'repo:{REPO} is:issue in:title "{title}"', "per_page": 30}
    lookup = session.get("https://api.github.com/search/issues",
                         headers=headers, params=params, timeout=TIMEOUT)
    lookup.raise_for_status()
    if any(x.get("title") == title for x in lookup.json().get("items", [])):
        print(f"Duplicate suppressed: {kind} {item['symbol']}")
        return False
    # Assign the repository owner to trigger a GitHub notification on mobile.
    # Notification delivery still depends on the user's GitHub settings.
    owner = REPO.split("/", 1)[0]
    result = session.post(
        base, headers=headers,
        json={"title": title, "body": body, "assignees": [owner]},
        timeout=TIMEOUT,
    )
    result.raise_for_status()
    print(f"Issue created: {result.json().get('html_url', 'issue')}") 
    return True


def run(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if not REPO or not TOKEN:
        print("GitHub issue logging disabled: GitHub token or repo missing")
        return 1
    active_asia = asia_session(now)
    active_us = market_session_open(now)
    if not active_asia and not active_us:
        print("Outside monitored market sessions")
        return 0
    signals = []
    if active_asia:
        for item in scan_once(now):
            signals.append(("ASIA", item))
    if active_us:
        for symbol in ("SPY", "QQQ"):
            try:
                item = fetch_and_assess(symbol, now)
                if item:
                    signals.append(("US", item))
            except Exception as exc:
                print(f"{symbol}: data unavailable ({type(exc).__name__})")
    if not signals:
        print("No verified qualifying completed-bar technical signals (data may be missing)")
        return 0
    with requests.Session() as session:
        for kind, item in signals:
            try:
                publish_issue(item, kind, now, session)
            except (requests.RequestException, ValueError, KeyError, RuntimeError) as exc:
                print(f"Issue publish failed: {type(exc).__name__}")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
