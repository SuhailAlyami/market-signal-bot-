"""Bounded, no-cost Yahoo research acquisition; never certifies a live feed.

Normal 7-day requests within Yahoo's recent minute-history window. Errors are
recorded without retries or fallback prices. Saved CSVs are the observed snapshot,
not a point-in-time archive of when a provider first published each candle.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

import pandas as pd
import yfinance as yf


def acquire(output: Path, weeks: int = 4, probe: bool = False) -> dict:
    if not 1 <= weeks <= 4:
        raise ValueError("Only 1–4 bounded weeks within recent history are supported")
    output.mkdir(parents=True, exist_ok=True)
    observed = datetime.now(timezone.utc)
    metadata = {
        "observed_at_utc": observed.isoformat(),
        "source": "Yahoo Finance via yfinance; potentially delayed, unofficial research interface",
        "live_feed_verified": False,
        "publication_latency_measured": False,
        "versions": {p: importlib.metadata.version(p) for p in ("pandas", "numpy", "yfinance")},
        "requests": [], "files": [],
    }
    for symbol in ("ES=F", "NQ=F"):
        frames = []
        for week in range(1 if probe else weeks):
            finish = observed.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7 * week)
            begin = finish - timedelta(days=7)
            request = {"symbol": symbol, "interval": "1m", "auto_adjust": False,
                       "request_started_utc": datetime.now(timezone.utc).isoformat()}
            started = time.monotonic()
            try:
                kwargs = {"period": "1d"} if probe else {"start": begin, "end": finish}
                request["parameters"] = {key: value.isoformat() if isinstance(value, datetime) else value
                                         for key, value in kwargs.items()}
                frame = yf.Ticker(symbol).history(interval="1m", auto_adjust=False, raise_errors=True, **kwargs)
                request["rows"] = len(frame)
                if frame.empty:
                    request["error"] = "empty_response"
                else:
                    if frame.index.tz is None:
                        raise ValueError("provider returned timezone-naive candles")
                    frame = frame[["Open", "High", "Low", "Close", "Volume"]].copy()
                    frame.index = frame.index.tz_convert("UTC")
                    frame.index.name = "timestamp"
                    request["first_bar_start_utc"] = frame.index.min().isoformat()
                    request["last_bar_start_utc"] = frame.index.max().isoformat()
                    completed = frame[frame.index + pd.Timedelta(minutes=1) <= pd.Timestamp(datetime.now(timezone.utc))]
                    if not completed.empty:
                        end = completed.index[-1] + pd.Timedelta(minutes=1)
                        request["last_completed_bar_end_utc"] = end.isoformat()
                        request["completed_bar_age_seconds"] = (datetime.now(timezone.utc) - end.to_pydatetime()).total_seconds()
                    frames.append(frame)
            except Exception as exc:
                # Exception messages can contain request URLs; save only safe type.
                request["error"] = type(exc).__name__
            request["request_finished_utc"] = datetime.now(timezone.utc).isoformat()
            request["request_duration_seconds"] = round(time.monotonic() - started, 3)
            metadata["requests"].append(request)
            print(json.dumps(request), flush=True)
        if frames and not probe:
            bars = pd.concat(frames).sort_index()
            duplicates = int(bars.index.duplicated().sum())
            bars = bars[~bars.index.duplicated(keep="last")]
            path = output / (symbol[:2].lower() + "_1m.csv.gz")
            bars.to_csv(path, compression={"method": "gzip", "mtime": 0})
            metadata["files"].append({"path": path.name, "rows": len(bars),
                                      "duplicates_removed": duplicates,
                                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    target = output / ("probe_" + observed.strftime("%Y%m%dT%H%M%SZ") + ".json" if probe else "acquisition.json")
    target.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--weeks", type=int, default=4)
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args()
    result = acquire(args.output, args.weeks, args.probe)
    if not any(r.get("rows", 0) for r in result["requests"]):
        raise SystemExit("No bars acquired; recorded failure, no fabricated data")
