"""Descriptive premium-event audit. No tuning or simulated option fills/P&L."""
import argparse
import hashlib
from datetime import timedelta
import json
from pathlib import Path

import pandas as pd

from premium_radar import features, classify_features, history_frame


def evaluate(data, horizon=5, target=0.25, delay_seconds=0, prepared=None, candidate=None):
    """Nonoverlapping +25% trade-price events; strict causal signal scheduling.

    Onset is the START of the first future minute whose high reaches +5%.
    Match by the START of the target minute, because intrabar timing is unknown.
    Historical bar availability is a scenario, not a measured real-time delay.
    """
    if horizon < 1 or target <= 0.05 or delay_seconds < 0:
        raise ValueError("invalid_evaluation_parameters")
    names = ("radar_watch", "radar_acceleration", "baseline_breakout", "baseline_momentum", "no_signal")
    if candidate is not None:
        names += ("candidate",)
    signals, events = {name: [] for name in names}, []
    cooldown = {}
    prepared = prepared if prepared is not None else [features(data, i) for i in range(len(data))]
    # Candidate scheduling is causal and happens before checking future labels.
    for i in range(20, len(data)):
        f = prepared[i]
        if f is None:
            continue
        signal = classify_features(f, data.index[i].to_pydatetime() + timedelta(minutes=1))
        rules = {"radar_watch": signal is not None and signal["state"] == "WATCH",
                 "radar_acceleration": signal is not None and signal["state"] == "ACCELERATION",
                 "baseline_breakout": f["price"] > f["prior_high"],
                 "baseline_momentum": f["return_1m"] >= 0.03, "no_signal": False}
        if candidate is not None:
            rules["candidate"] = bool(candidate(f))
        decision = data.index[i] + pd.Timedelta(minutes=1, seconds=delay_seconds)
        for name, active in rules.items():
            if active and (name not in cooldown or decision >= cooldown[name]):
                cooldown[name] = decision + pd.Timedelta(minutes=horizon)
                end = i + horizon
                observable = end < len(data) and (
                    data.index[i:end+1].to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all() and all(
                        prepared[j] is not None for j in range(i+1, end+1))
                signals[name].append({"index": i, "decision": decision, "censored": not observable})
    i = 20
    while i + horizon < len(data):
        sample = data.iloc[i:i+horizon+1]
        valid_window = (prepared[i] is not None
                        and (sample.index.to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all()
                        and all(prepared[j] is not None for j in range(i+1, i+horizon+1)))
        if not valid_window:
            i += 1
            continue
        anchor = float(data.Close.iloc[i])
        target_bars = [j for j in range(i+1, i+horizon+1) if data.High.iloc[j] >= anchor * (1+target)]
        if not target_bars:
            i += 1
            continue
        hit = target_bars[0]
        onset = next(j for j in range(i+1, hit+1) if data.High.iloc[j] >= anchor * 1.05)
        events.append({"anchor": data.index[i] + pd.Timedelta(minutes=1),
                       "onset": data.index[onset], "target": data.index[hit]})
        i = hit + 1
    metrics = {}
    for name, rows in signals.items():
        scored = [row for row in rows if not row["censored"]]
        used, lead = set(), []
        for row in scored:
            for k, event in enumerate(events):
                generated = data.index[row['index']] + pd.Timedelta(minutes=1)
                if (k not in used and event["anchor"] <= generated
                        and row["decision"] <= event["target"]):
                    used.add(k)
                    lead.append((event["onset"] - row["decision"]).total_seconds())
                    break
        early = sum(seconds > 0 for seconds in lead)
        metrics[name] = {"signals": len(scored), "censored_signals": len(rows)-len(scored),
                         "detected_events": len(lead), "early_events": early,
                         "event_precision": len(lead)/len(scored) if scored else None,
                         "event_recall": len(lead)/len(events) if events else None,
                         "early_recall": early/len(events) if events else None,
                         "false_alarms": len(scored)-len(lead), "missed_events": len(events)-len(lead),
                         "median_lead_seconds": float(pd.Series(lead).median()) if lead else None}
    return {"bars": len(data), "independent_events": len(events), "methods": metrics,
            "horizon_minutes": horizon, "premium_target_pct": target*100,
            "availability_delay_seconds": delay_seconds}


def study(raw):
    data = history_frame(raw)
    prepared = [features(data, i) for i in range(len(data))]
    days = sorted(set(data.index.tz_convert("America/New_York").date))
    result = {"decision": "NOT_READY", "source": "IBKR option last-trade OHLCV",
              "observed_ny_calendar_dates": [str(day) for day in days],
              "descriptive_all_data": [evaluate(data, delay_seconds=delay, prepared=prepared) for delay in (0, 60, 120)],
              "holdout": None,
              "limitations": ["Trade highs are not executable option bid/ask or fills.",
                              "Fixed exploratory rules; no calibrated prediction probability or profitability claim.",
                              "One selected near-ATM contract has survivorship/selection and changing-DTE bias.",
                              "Provider publication/arrival times are not supplied by historical bars.",
                              "No commissions, spread, slippage, fills or option P&L are simulated."]}
    if len(days) < 5:
        result["reason"] = "insufficient_sessions_for_train_validation_holdout"
        return result
    # Freeze thresholds; whole NY dates avoid train/test overlap. Embargo edges
    # cover the complete 20-bar lookback plus the 5-minute outcome horizon.
    partitions = {"train": days[:-2], "validation": days[-2:-1], "test": days[-1:]}
    reports = {}
    local_days = data.index.tz_convert("America/New_York").date
    for name, dates in partitions.items():
        section = data[[day in dates for day in local_days]]
        section = section.iloc[25:-5] if len(section) > 30 else section.iloc[:0]
        reports[name] = evaluate(section)
    result.update(partitions={key: [str(d) for d in value] for key, value in partitions.items()},
                  holdout=reports, reason="research_only_requires_independent_replication")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    source = Path(args.input).read_bytes()
    report = study(json.loads(source))
    report["source_sha256"] = hashlib.sha256(source).hexdigest()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report, indent=2, allow_nan=False))
