"""Read-only SPX collection through an authenticated IBKR MCP session.

No orders, account queries, synthetic quotes or Yahoo fallback. The transport
is injectable, so the connected assistant and a separately authorized runtime
use the same validation. Last-trade timestamps NEVER certify bid/ask freshness.
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
from zoneinfo import ZoneInfo

from spx_option_selector import OptionQuote, select_spx_0dte

SOURCE = "IBKR MCP"
ENDPOINT = "https://api.ibkr.com/v1/api/mcp-public"
READ_TOOLS = frozenset({"search_contracts", "get_price_snapshot", "get_option_parameters",
                        "get_option_data", "get_price_history"})
NY = ZoneInfo("America/New_York")


def unwrap(result):
    """Accept MCP SDK results and connector envelopes, including JSON text."""
    if hasattr(result, "model_dump"):
        result = result.model_dump(by_alias=True)
    if not isinstance(result, dict):
        raise ValueError("invalid_tool_result")
    if result.get("isError") or result.get("is_error"):
        raise ValueError("tool_error")
    structured = result.get("structuredContent", result.get("structured_content"))
    if isinstance(structured, dict):
        return structured
    if "content" in result:
        text = [block.get("text", "") for block in result["content"]
                if isinstance(block, dict) and block.get("type") == "text"]
        if len(text) != 1:
            raise ValueError("ambiguous_tool_result")
        parsed = json.loads(text[0])
        if not isinstance(parsed, dict):
            raise ValueError("invalid_tool_result")
        return parsed
    return result


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def stamp(value):
    if not finite(value):
        return None
    try:
        return datetime.fromtimestamp(value, timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def age(time, now):
    return None if time is None else (now - time).total_seconds()


def inspect_snapshot(raw, now, max_age_seconds=10):
    """Separate feed entitlement/type, last trade and bid/ask timestamps."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("aware_clock_required")
    if not finite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("invalid_max_age")
    raw = unwrap(raw)
    last = raw.get("last") or {}
    book = raw.get("bid-ask") or {}
    state = (raw.get("top-status") or {}).get("status", "UNAVAILABLE")
    last_time = stamp(last.get("ts"))
    # Only a timestamp explicitly attached to the bid/ask object is relevant.
    # Do not reuse last.ts or the collector's wall clock for this field.
    quote_time = stamp(book.get("ts"))
    last_age, quote_age = age(last_time, now), age(quote_time, now)
    price, bid, ask = last.get("price"), book.get("bid"), book.get("ask")
    valid_last = finite(price) and price > 0
    valid_book = all(finite(x) for x in (bid, ask)) and bid > 0 and ask >= bid
    last_verified = (state == "REALTIME" and valid_last and last_age is not None
                     and 0 <= last_age <= max_age_seconds)
    quote_verified = (state == "REALTIME" and valid_book and quote_age is not None
                      and 0 <= quote_age <= max_age_seconds)
    return {"source": SOURCE, "feed_status": state,
            "last": price if valid_last else None,
            "last_trade_at": last_time.isoformat() if last_time else None,
            "last_trade_age_seconds": last_age, "last_live_verified": last_verified,
            "bid": bid if valid_book else None, "ask": ask if valid_book else None,
            "quote_at": quote_time.isoformat() if quote_time else None,
            "quote_age_seconds": quote_age, "quote_live_verified": quote_verified,
            "quote_reason": ("verified" if quote_verified else
                             "invalid_bid_ask" if not valid_book else
                             "feed_not_realtime" if state != "REALTIME" else
                             "missing_bid_ask_timestamp" if quote_time is None else
                             "stale_or_future_bid_ask_timestamp")}


async def collect_spx(call, *, now=None, clock=None, max_age_seconds=10, strikes_per_side=2, history_sink=None):
    """Collect today's SPXW near-ATM contracts; bounded read-only calls.

    call(name, arguments) must enforce READ_TOOLS at the transport boundary.
    now freezes the clock for deterministic tests; live runs use receipt time.
    A frozen index may center a RESEARCH chain query, never certify a candidate.
    """
    if not finite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("invalid_max_age")
    if not isinstance(strikes_per_side, int) or not 1 <= strikes_per_side <= 3:
        raise ValueError("invalid_strike_count")
    fixed = now
    clock = clock or (lambda: datetime.now(timezone.utc))
    receipt = lambda: fixed if fixed is not None else clock()
    started = receipt()
    if started.tzinfo is None or started.utcoffset() is None:
        raise ValueError("aware_clock_required")
    report = {"schema_version": 1, "source": SOURCE, "orders_enabled": False,
              "readiness": "NOT_READY", "status": "collecting", "contracts": [],
              "started_at": started.isoformat(), "candidates": {}}

    async def read(name, arguments):
        if name not in READ_TOOLS:
            raise ValueError("read_only_tool_denied")
        return unwrap(await call(name, arguments))

    try:
        found = await read("search_contracts", {"query": "SPX"})
        matches = [x for x in found.get("results", []) if x.get("symbol") == "SPX"
                   and x.get("exchange") == "CBOE" and x.get("country_code") == "US"
                   and {s.get("security_type") for s in x.get("sections", [])} >= {"IND", "OPT"}]
        if len(matches) != 1:
            raise ValueError("ambiguous_spx_index")
        contract_id = matches[0]["underlying_contract_id"]
        index_raw = await read("get_price_snapshot", {"contract_id": contract_id,
                              "exchange": "CBOE", "market_data_names": ["last", "bid_ask", "top_status"]})
        index = inspect_snapshot(index_raw, receipt(), max_age_seconds)
        report["underlying"] = index
        spot = index["last"]
        if spot is None:
            report.update(status="unavailable", reason="missing_spx_reference_price")
            return report
        params = await read("get_option_parameters", {"underlying_contract_id": contract_id,
                                                       "option_sec_type": "OPT"})
        date = receipt().astimezone(NY).strftime("%Y%m%d")
        expiry = [x for x in params.get("expirations", [])
                  if x.get("date") == date and x.get("trading_class") == "SPXW"]
        if len(expiry) != 1:
            report.update(status="unavailable", reason="no_unique_today_spxw_expiry")
            return report
        chain = await read("get_option_data", {"expiration_id": expiry[0]["id"],
                                               "min_strike": spot - 40, "max_strike": spot + 40})
        exchange = chain.get("exchange")
        if not exchange or chain.get("currency") != "USD":
            raise ValueError("invalid_option_chain_metadata")
        rows = sorted(chain.get("contracts", []), key=lambda x: abs(float(x["strike"]) - spot))
        if not rows:
            report.update(status="unavailable", reason="empty_option_chain")
            return report
        quotes = {"CALL": [], "PUT": []}
        expiry_iso = datetime.strptime(date, "%Y%m%d").date().isoformat()
        for row in rows[:strikes_per_side]:
            for side, prefix, right in (("CALL", "call", "C"), ("PUT", "put", "P")):
                raw = await read("get_price_snapshot", {"contract_id": row[prefix + "_contract_id"],
                                 "exchange": exchange, "market_data_names": ["last", "bid_ask", "top_status"]})
                quote = inspect_snapshot(raw, receipt(), max_age_seconds)
                entry = {"symbol": "SPX", "trading_class": "SPXW", "expiry": expiry_iso,
                         "strike": float(row["strike"]), "side": side, "exchange": exchange,
                         "description": row[prefix + "_description"], **quote}
                report["contracts"].append(entry)
                if quote["quote_live_verified"]:
                    quotes[side].append(OptionQuote(
                        symbol="SPX", expiry=expiry_iso, right=right, strike=entry["strike"],
                        bid=quote["bid"], ask=quote["ask"], source=SOURCE, live_verified=True,
                        quote_time=datetime.fromisoformat(quote["quote_at"])))
        # Observe actual option-premium acceleration independently of the
        # executable-quote gate. Only the nearest strike is queried for history
        # to bound API usage. These hypotheses cannot send notifications.
        from premium_radar import assess_history
        report["premium_radar"] = []
        nearest = rows[0]
        for side, prefix in (("CALL", "call"), ("PUT", "put")):
            try:
                raw_history = await read("get_price_history", {
                    "contract_id": nearest[prefix + "_contract_id"], "exchange": exchange,
                    "security_type": "OPT", "outside_rth": True, "step": "ONE_MIN", "step_count": 90})
                book = next(entry for entry in report["contracts"]
                            if entry["side"] == side and entry["strike"] == float(nearest["strike"]))
                if history_sink is not None:
                    history_sink({"contract_id": nearest[prefix + "_contract_id"], "exchange": exchange,
                                  "expiry": expiry_iso, "strike": float(nearest["strike"]),
                                  "side": side, "feed_status": book["feed_status"]}, raw_history, receipt())
                observation = assess_history(raw_history, now=receipt(), feed_status=book["feed_status"])
            except Exception as exc:
                observation = {"status": "unavailable", "reason": "premium_history_failed",
                               "error_type": type(exc).__name__, "signal": None,
                               "research_only": True, "notifications_enabled": False}
            report["premium_radar"].append({"side": side, "strike": float(nearest["strike"]),
                                            "expiry": expiry_iso, **observation})
        finished = receipt()
        # Revalidate index age after all calls; don't grant freshness based on
        # a timestamp captured before a slow option-chain collection.
        report["underlying"] = inspect_snapshot(index_raw, finished, max_age_seconds)
        candidates = {}
        for side in quotes:
            selected = select_spx_0dte(
                quotes[side], direction=side, underlying=spot, now=finished,
                underlying_time=datetime.fromisoformat(index["last_trade_at"]) if index["last_trade_at"] else finished,
                underlying_live_verified=report["underlying"]["last_live_verified"],
                max_age_seconds=max_age_seconds)
            if selected:
                candidates[side] = asdict(selected)
        report.update(status="collected", observed_at=finished.isoformat(),
                      candidates=candidates, reason="research_only_no_validated_strategy")
        if candidates:
            report["readiness"] = "RESEARCH_ONLY"
        else:
            report["reason"] = ("underlying_not_fresh_realtime" if not report["underlying"]["last_live_verified"]
                                else "no_timestamp_verified_option_quotes")
    except Exception as exc:
        # Never persist provider messages that could include auth headers/URLs.
        report.update(status="error", readiness="NOT_READY", error_type=type(exc).__name__,
                      reason="collection_failed", candidates={})
    finally:
        report["observed_at"] = receipt().isoformat()
    return report


def save_report(report, path):
    """Atomic, private market-data report. No tokens or account fields."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def report_health(path, now=None, max_report_age=180):
    """Public health metadata only; quotes and OAuth state stay private."""
    now = now or datetime.now(timezone.utc)
    try:
        report = json.loads(Path(path).read_text())
        observed = datetime.fromisoformat(report["observed_at"])
        elapsed = (now - observed).total_seconds()
        return {"status": report["status"] if 0 <= elapsed <= max_report_age else "stale_report",
                "readiness": report["readiness"] if 0 <= elapsed <= max_report_age else "NOT_READY",
                "source": SOURCE, "observed_at": report["observed_at"],
                "report_age_seconds": elapsed, "orders_enabled": False,
                "underlying_feed_status": report.get("underlying", {}).get("feed_status"),
                "premium_signal_count": sum(bool(item.get("signal")) for item in report.get("premium_radar", [])),
                "premium_bar_versions_recorded": report.get("premium_bar_versions_recorded", 0),
                "premium_outcomes": {key: report.get("premium_outcomes", {}).get(key, 0)
                                     for key in ("scored", "censored", "pending", "target_hits")},
                "experimental_notifications_enabled": False,
                "reason": report.get("reason")}
    except (OSError, ValueError, KeyError, TypeError):
        return {"status": "unavailable", "readiness": "NOT_READY", "source": SOURCE,
                "orders_enabled": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize", action="store_true", help="allow a local browser OAuth sign-in")
    parser.add_argument("--output", default=os.getenv("IBKR_MCP_REPORT", ".hunter-state/ibkr_snapshot.json"))
    args = parser.parse_args()
    from ibkr_mcp_client import run_collection
    report = asyncio.run(run_collection(authorize=args.authorize))
    save_report(report, args.output)
    print(json.dumps(report_health(args.output), ensure_ascii=False))
    return 1 if report["status"] == "error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
