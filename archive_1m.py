"""Archive free 1-minute bars. No orders and no paid subscription.

Yahoo (default, also the GitHub schedule) writes one file per New York
session date:

    data/archive/<folder>/<YYYY-MM-DD>.csv.gz

An existing day file is never rewritten. A later different payload is reported
and left untouched. The in-progress session is skipped until 20:05 America/New_York,
after the 20:00 extended-hours close, so the first commit is a full pre/regular/post
day when Yahoo has those prints.

IBKR is local only. It needs TWS or IB Gateway already open on this machine.
It requests delayed data (market data type 3, then 4) and does not require a
paid real-time subscription. Historical bars share the receipt time of the
response. Live updates, if --live-seconds is set, are appended with their own
receipt time under data/archive/ibkr/<folder>/live-<day>.jsonl.
Permission failures are logged and do not stop the other symbols.

This environment cannot open a live IBKR session. The socket client is covered
by mocked unit tests only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
COLUMNS = ("timestamp", "Open", "High", "Low", "Close", "Volume", "received_at", "timing")
YAHOO = (
    ("SPY", "SPY"),
    ("^GSPC", "GSPC"),
    ("QQQ", "QQQ"),
    ("^VIX", "VIX"),
    ("^VIX1D", "VIX1D"),
)
IBKR_SPECS = (
    {"folder": "SPY", "symbol": "SPY", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary": "ARCA"},
    {"folder": "QQQ", "symbol": "QQQ", "sec_type": "STK", "exchange": "SMART", "currency": "USD", "primary": "NASDAQ"},
    {"folder": "SPX", "symbol": "SPX", "sec_type": "IND", "exchange": "CBOE", "currency": "USD", "primary": ""},
    {"folder": "VIX", "symbol": "VIX", "sec_type": "IND", "exchange": "CBOE", "currency": "USD", "primary": ""},
)
INFO_CODES = {2104, 2106, 2107, 2108, 2119, 2158, 2176}
PERMISSION_CODES = {354, 10089, 10167, 10197}


def folders_to_symbols() -> dict[str, str]:
    return {folder: symbol for symbol, folder in YAHOO}


def day_ready(day, now: datetime) -> bool:
    """True once that New York date is finished through the extended session."""
    local = now.astimezone(NY)
    if day < local.date():
        return True
    if day > local.date():
        return False
    return local.hour * 60 + local.minute >= 20 * 60 + 5


def is_permission_error(code: int, message: str) -> bool:
    text = (message or "").lower()
    if int(code) in PERMISSION_CODES:
        return True
    if int(code) == 162 and any(phrase in text for phrase in (
        "permission", "not subscribed", "subscription", "no market data",
    )):
        return True
    return any(phrase in text for phrase in (
        "no market data permissions", "not subscribed", "requires additional subscription",
    ))


def _csv_text(rows: list[dict]) -> str:
    lines = [",".join(COLUMNS)]
    for row in sorted(rows, key=lambda item: item["timestamp"]):
        ts = row["timestamp"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        received = row["received_at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        lines.append(
            f"{ts},{row['Open']:.10g},{row['High']:.10g},{row['Low']:.10g},"
            f"{row['Close']:.10g},{row['Volume']:.10g},{received},{row['timing']}"
        )
    return "\n".join(lines) + "\n"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def store_days(folder: Path, rows: list[dict], now: datetime) -> dict:
    """Write new session files. Never replace an existing day."""
    folder.mkdir(parents=True, exist_ok=True)
    grouped: dict = {}
    for row in rows:
        grouped.setdefault(row["timestamp"].astimezone(NY).date(), []).append(row)
    stored, skipped, conflicts, pending = [], [], [], []
    for day, day_rows in sorted(grouped.items()):
        path = folder / f"{day.isoformat()}.csv.gz"
        payload = _csv_text(day_rows)
        if not day_ready(day, now):
            pending.append(day.isoformat())
            continue
        if path.exists():
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                current = handle.read()
            if _sha(current) == _sha(payload):
                skipped.append(day.isoformat())
            else:
                conflicts.append(day.isoformat())
            continue
        temporary = path.with_suffix(".csv.gz.tmp")
        with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(temporary, path)
        stored.append({"day": day.isoformat(), "rows": len(day_rows), "sha256": _sha(payload)})
    return {"stored": stored, "unchanged": skipped, "conflicts": conflicts, "pending": pending}


def append_live(folder: Path, rows: list[dict]) -> int:
    """Append first-seen live bars. The same timestamp is not written twice."""
    if not rows:
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    by_day: dict = {}
    for row in rows:
        by_day.setdefault(row["timestamp"].astimezone(NY).date(), []).append(row)
    added = 0
    for day, day_rows in by_day.items():
        path = folder / f"live-{day.isoformat()}.jsonl"
        seen = set()
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        seen.add(json.loads(line)["timestamp"])
                    except (json.JSONDecodeError, KeyError):
                        continue
        with path.open("a", encoding="utf-8") as handle:
            for row in day_rows:
                stamp = row["timestamp"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                if stamp in seen:
                    continue
                seen.add(stamp)
                handle.write(json.dumps({
                    "timestamp": stamp,
                    "Open": row["Open"], "High": row["High"], "Low": row["Low"],
                    "Close": row["Close"], "Volume": row["Volume"],
                    "received_at": row["received_at"].astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    "timing": "live_update",
                }) + "\n")
                added += 1
    return added


def _write_manifest(out_dir: Path, updates: list[dict]) -> None:
    path = out_dir / "manifest.json"
    current = {"days": []}
    if path.exists():
        current = json.loads(path.read_text(encoding="utf-8"))
    known = {(item["source"], item["folder"], item["day"]) for item in current.get("days", [])}
    for item in updates:
        key = (item["source"], item["folder"], item["day"])
        if key not in known:
            current.setdefault("days", []).append(item)
            known.add(key)
    path.write_text(json.dumps(current, indent=2), encoding="utf-8")


def yahoo_bars(symbol: str, sleep: float = 0.35) -> tuple[list[dict], list[dict]]:
    rows: dict[int, dict] = {}
    notes = []
    end = int(time.time())
    for _ in range(6):
        start = end - 8 * 86400
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol, safe='')}"
            f"?interval=1m&period1={start}&period2={end}&includePrePost=true"
        )
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (research archive)"})
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                body = response.read()
                status = response.status
        except Exception as exc:
            notes.append({"symbol": symbol, "period1": start, "error": type(exc).__name__, "detail": str(exc)[:180]})
            break
        received = datetime.now(timezone.utc)
        document = json.loads(body)
        result = (document.get("chart", {}).get("result") or [None])[0]
        timestamps = result.get("timestamp") if result else None
        if not timestamps:
            notes.append({"symbol": symbol, "period1": start, "error": "empty", "status": status})
            break
        quote = result["indicators"]["quote"][0]
        kept = 0
        for i, epoch in enumerate(timestamps):
            values = [quote[name][i] for name in ("open", "high", "low", "close", "volume")]
            if any(value is None for value in values):
                continue
            rows[int(epoch)] = {
                "timestamp": datetime.fromtimestamp(int(epoch), timezone.utc),
                "Open": float(values[0]), "High": float(values[1]), "Low": float(values[2]),
                "Close": float(values[3]), "Volume": float(values[4]),
                "received_at": received, "timing": "yahoo_response",
            }
            kept += 1
        notes.append({"symbol": symbol, "status": status, "rows": kept, "received_at": received.isoformat(),
                      "last_bar_age_seconds": round(received.timestamp() - timestamps[-1], 3)})
        end = start
        if sleep:
            time.sleep(sleep)
    return [rows[key] for key in sorted(rows)], notes


def archive_yahoo(out_dir: Path, now: datetime | None = None, sleep: float = 0.35) -> dict:
    now = now or datetime.now(timezone.utc)
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {"source": "yahoo", "stored": [], "conflicts": [], "pending": [], "notes": []}
    manifest_rows = []
    for symbol, folder in YAHOO:
        bars, notes = yahoo_bars(symbol, sleep=sleep)
        report["notes"].extend(notes)
        if not bars:
            continue
        outcome = store_days(out_dir / folder, bars, now)
        for item in outcome["stored"]:
            item.update(source="yahoo", folder=folder, symbol=symbol)
            manifest_rows.append(item)
        report["stored"].extend(outcome["stored"])
        report["conflicts"].extend(f"{folder}:{day}" for day in outcome["conflicts"])
        report["pending"].extend(f"{folder}:{day}" for day in outcome["pending"])
    if manifest_rows:
        _write_manifest(out_dir, manifest_rows)
    return report


def collect_ibkr(client, out_dir: Path, now: datetime, use_rth: int = 0) -> dict:
    """Pull whatever delayed history the injected client can return. No orders."""
    out_dir.mkdir(parents=True, exist_ok=True)
    client.set_market_data_type(3)
    report = {
        "source": "ibkr",
        "market_data_type_requested": 3,
        "market_data_type_seen": getattr(client, "market_data_type", None),
        "use_rth": use_rth,
        "permission_missing": [],
        "unavailable": [],
        "stored": [],
        "conflicts": [],
        "live_appended": 0,
    }
    manifest_rows = []
    for spec in IBKR_SPECS:
        outcome = client.history(spec, use_rth=use_rth, what_to_show="TRADES")
        if not outcome.bars and spec["sec_type"] == "IND":
            alternate = client.history(spec, use_rth=use_rth, what_to_show="MIDPOINT")
            if alternate.bars:
                outcome = alternate
            else:
                outcome.errors.extend(alternate.errors)
        permission = [item for item in outcome.errors if is_permission_error(item.get("code", 0), item.get("message", ""))]
        if not outcome.bars and permission:
            report["permission_missing"].append({"symbol": spec["folder"], "errors": permission})
            continue
        if not outcome.bars:
            report["unavailable"].append({"symbol": spec["folder"], "errors": outcome.errors})
            continue
        folder = out_dir / "ibkr" / spec["folder"]
        stored = store_days(folder, outcome.bars, now)
        report["live_appended"] += append_live(folder, outcome.live_bars)
        for item in stored["stored"]:
            item.update(source="ibkr", folder=spec["folder"], symbol=spec["symbol"])
            manifest_rows.append(item)
        report["stored"].extend(stored["stored"])
        report["conflicts"].extend(f"ibkr/{spec['folder']}:{day}" for day in stored["conflicts"])
    if manifest_rows:
        _write_manifest(out_dir, manifest_rows)
    return report


def _contract(spec: dict):
    from ibapi.contract import Contract
    contract = Contract()
    contract.symbol = spec["symbol"]
    contract.secType = spec["sec_type"]
    contract.exchange = spec["exchange"]
    contract.currency = spec["currency"]
    if spec.get("primary"):
        contract.primaryExchange = spec["primary"]
    return contract


def _parse_bar_time(value: str) -> datetime:
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), timezone.utc)
    raise ValueError(f"unsupported_bar_time:{text}")


class _IbkrApp:
    """Thin EWrapper. Imported only when a live local session starts."""

    def __init__(self):
        from ibapi.client import EClient
        from ibapi.wrapper import EWrapper

        class App(EWrapper, EClient):
            def __init__(self):
                EWrapper.__init__(self)
                EClient.__init__(self, self)
                self.ready = threading.Event()
                self.kind = None
                self.errors = []
                self.buckets = {}

            def nextValidId(self, orderId):
                self.ready.set()

            def marketDataType(self, reqId, marketDataType):
                self.kind = int(marketDataType)

            def error(self, reqId, errorCode, errorString, *extra):
                code = int(errorCode)
                if code in INFO_CODES:
                    return
                self.errors.append({
                    "reqId": reqId, "code": code, "message": str(errorString),
                    "received_at": datetime.now(timezone.utc).isoformat(),
                })
                bucket = self.buckets.get(reqId)
                if bucket is not None and (is_permission_error(code, str(errorString)) or code in (200, 162, 321, 322)):
                    bucket["done"].set()

            def historicalData(self, reqId, bar):
                bucket = self.buckets.get(reqId)
                if bucket is None:
                    return
                try:
                    stamp = _parse_bar_time(bar.date)
                except ValueError:
                    return
                bucket["bars"].append({
                    "timestamp": stamp,
                    "Open": float(bar.open), "High": float(bar.high),
                    "Low": float(bar.low), "Close": float(bar.close),
                    "Volume": float(getattr(bar, "volume", 0) or 0),
                })

            def historicalDataUpdate(self, reqId, bar):
                bucket = self.buckets.get(reqId)
                if bucket is None:
                    return
                try:
                    stamp = _parse_bar_time(bar.date)
                except ValueError:
                    return
                bucket["live"].append({
                    "timestamp": stamp,
                    "Open": float(bar.open), "High": float(bar.high),
                    "Low": float(bar.low), "Close": float(bar.close),
                    "Volume": float(getattr(bar, "volume", 0) or 0),
                    "received_at": datetime.now(timezone.utc),
                    "timing": "live_update",
                })

            def historicalDataEnd(self, reqId, start, end):
                bucket = self.buckets.get(reqId)
                if bucket is not None:
                    bucket["received_at"] = datetime.now(timezone.utc)
                    bucket["done"].set()

        self.app = App()

    def connect(self, host: str, port: int, client_id: int, timeout: float) -> None:
        worker = threading.Thread(target=self._run, args=(host, port, client_id), daemon=True)
        worker.start()
        if not self.app.ready.wait(timeout):
            self.close()
            raise RuntimeError("ibkr_handshake_timeout")

    def _run(self, host, port, client_id):
        try:
            self.app.connect(host, port, clientId=client_id)
            self.app.run()
        except Exception:
            return

    def close(self) -> None:
        try:
            self.app.disconnect()
        except Exception:
            pass

    def set_market_data_type(self, kind: int) -> None:
        self.app.reqMarketDataType(int(kind))
        self.market_data_type = kind

    def history(self, spec: dict, use_rth: int, what_to_show: str, days: int = 5, pause: float = 11.0) -> "HistoryOutcome":
        outcome = HistoryOutcome()
        today = datetime.now(NY).date()
        req = 5000 + (abs(hash(spec["folder"] + what_to_show)) % 1000)
        for offset in range(1, days + 1):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:
                continue
            end = f"{day.strftime('%Y%m%d')} 20:00:00 US/Eastern"
            bucket = {"bars": [], "live": [], "done": threading.Event(), "received_at": None}
            req_id = req + offset
            self.app.buckets[req_id] = bucket
            before = len(self.app.errors)
            self.app.reqHistoricalData(
                req_id, _contract(spec), end, "1 D", "1 min", what_to_show,
                int(use_rth), 2, False, [],
            )
            bucket["done"].wait(25)
            try:
                self.app.cancelHistoricalData(req_id)
            except Exception:
                pass
            received = bucket["received_at"] or datetime.now(timezone.utc)
            for bar in bucket["bars"]:
                bar["received_at"] = received
                bar["timing"] = "historical_batch"
                outcome.bars.append(bar)
            outcome.live_bars.extend(bucket["live"])
            outcome.errors.extend(self.app.errors[before:])
            if pause:
                time.sleep(pause)
        return outcome


class HistoryOutcome:
    def __init__(self):
        self.bars: list[dict] = []
        self.live_bars: list[dict] = []
        self.errors: list[dict] = []


class LiveIbkrClient:
    def __init__(self, host: str, port: int, client_id: int, days: int, pause: float):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.days = days
        self.pause = pause
        self.market_data_type = None
        self._session: _IbkrApp | None = None

    def connect(self) -> None:
        try:
            import ibapi  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("ibapi_not_installed") from exc
        self._session = _IbkrApp()
        self._session.connect(self.host, self.port, self.client_id, timeout=12)

    def set_market_data_type(self, kind: int) -> None:
        if self._session is None:
            raise RuntimeError("ibkr_not_connected")
        self._session.set_market_data_type(kind)
        self.market_data_type = kind

    def history(self, spec: dict, use_rth: int, what_to_show: str) -> HistoryOutcome:
        if self._session is None:
            raise RuntimeError("ibkr_not_connected")
        return self._session.history(spec, use_rth=use_rth, what_to_show=what_to_show, days=self.days, pause=self.pause)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()


def archive_ibkr(out_dir: Path, now: datetime | None = None, host: str = "127.0.0.1", port: int = 4001,
                 client_id: int = 21011, use_rth: int = 0, days: int = 5, pause: float = 11.0,
                 client=None) -> dict:
    now = now or datetime.now(timezone.utc)
    owns_client = client is None
    if client is None:
        client = LiveIbkrClient(host, port, client_id, days, pause)
        client.connect()
    try:
        report = collect_ibkr(client, out_dir, now, use_rth=use_rth)
    finally:
        if owns_client:
            client.close()
    report["host"] = host
    report["port"] = port
    report["delayed_only"] = True
    report["paid_subscription"] = False
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive free 1-minute bars")
    parser.add_argument("--source", choices=("yahoo", "ibkr"), default="yahoo")
    parser.add_argument("--out", default="data/archive")
    parser.add_argument("--host", default=os.getenv("IBKR_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("IBKR_PORT", "4001")))
    parser.add_argument("--client-id", type=int, default=int(os.getenv("IBKR_CLIENT_ID", "21011")))
    parser.add_argument("--use-rth", type=int, choices=(0, 1), default=0,
                        help="IBKR reqHistoricalData useRTH. 0 keeps outside regular hours when the feed allows it.")
    parser.add_argument("--days", type=int, default=5, help="Completed sessions to request from IBKR.")
    args = parser.parse_args()
    out = Path(args.out)
    try:
        if args.source == "yahoo":
            report = archive_yahoo(out)
        else:
            report = archive_ibkr(
                out, host=args.host, port=args.port, client_id=args.client_id,
                use_rth=args.use_rth, days=args.days,
            )
    except RuntimeError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, default=str))
    if report.get("permission_missing"):
        print("NO_PERMISSION " + ",".join(item["symbol"] for item in report["permission_missing"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
