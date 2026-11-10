"""Small predeclared grid for the legacy 5-minute confirmation.

Uses the same 1-minute explosion definition, chronological split, 60-second
decision delay and one-cent share cost as research_1m_lead.py. Validation
selects. The isolated test is scored only for the current defaults and the
selected candidate.

Defaults change only when that test's early-recall interval and lead interval
both sit entirely above the default intervals, without a worse hit-rate interval
or a material rise in false alarms. This file does not read the test to choose
the grid.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_1m_lead import (
    build_events,
    drop_partial_last_session,
    evaluate,
    five_minute_atr,
    legacy_signals,
    load_frame,
    rth_sessions,
    split_sessions,
)

LOOKBACKS = (15, 30, 45)
RVOLS = (1.5, 2.0, 2.5)
MOMENTUMS = (0.15, 0.25, 0.35)
DISTANCES = (0.05, 0.10, 0.20)
DEFAULT = {"lookback": 30, "rvol_min": 2.0, "momentum_pct": 0.35, "min_distance_atr": 0.1}


def grid() -> list[dict]:
    rows = []
    for lookback in LOOKBACKS:
        for rvol in RVOLS:
            for momentum in MOMENTUMS:
                for distance in DISTANCES:
                    rows.append({
                        "lookback": lookback,
                        "rvol_min": rvol,
                        "momentum_pct": momentum,
                        "min_distance_atr": distance,
                    })
    return rows


def config_name(cfg: dict) -> str:
    return f"lb{cfg['lookback']}_rv{cfg['rvol_min']:.1f}_m{cfg['momentum_pct']:.2f}_d{cfg['min_distance_atr']:.2f}"


def _close_enough(row: dict, baseline: dict) -> bool:
    if not row.get("signals"):
        return False
    base_hit = baseline.get("forward_hit_rate")
    hit = row.get("forward_hit_rate")
    if base_hit not in (None, 0) and (hit is None or hit < 0.8 * base_hit):
        return False
    base_fa = baseline.get("false_alarms_per_session")
    fa = row.get("false_alarms_per_session")
    if base_fa is not None and fa is not None and fa > base_fa + 0.5:
        return False
    return True


def _rank(row: dict) -> tuple:
    return (
        row.get("recall_before_onset") if row.get("recall_before_onset") is not None else -1,
        row.get("median_lead_min") if row.get("median_lead_min") is not None else -999,
        -(row.get("false_alarms_per_session") or 0),
        row.get("forward_hit_rate") if row.get("forward_hit_rate") is not None else -1,
    )


def select_legacy(rows: list[dict], baseline: dict) -> dict:
    eligible = [row for row in rows if _close_enough(row, baseline)]
    pool = eligible or []
    if not pool:
        return {"selected": config_name(DEFAULT), "constrained": False, "reason": "no candidate stayed close to the default hit rate and false alarms"}
    pool.sort(key=_rank, reverse=True)
    winner = pool[0]
    return {
        "selected": winner["name"],
        "constrained": True,
        "eligible": len(pool),
        "reason": "validation early recall, then lead, among candidates close to the default hit rate and false alarms",
    }


def promote_legacy(candidate: dict | None, baseline: dict) -> dict:
    if candidate is None or candidate.get("name") == config_name(DEFAULT):
        return {"promote": False, "reason": "selected candidate is the current default or missing"}
    recall = candidate.get("recall_before_onset_wilson95")
    base_recall = baseline.get("recall_before_onset_wilson95")
    lead = candidate.get("median_lead_bootstrap95")
    base_lead = baseline.get("median_lead_bootstrap95")
    hit = candidate.get("forward_hit_wilson95")
    base_hit = baseline.get("forward_hit_wilson95")
    separated_recall = bool(recall and base_recall and recall[0] > base_recall[1])
    separated_lead = bool(lead and base_lead and lead[0] > base_lead[1])
    hit_ok = bool(hit and base_hit and hit[1] >= base_hit[0])
    fa_ok = (
        candidate.get("false_alarms_per_session") is not None
        and baseline.get("false_alarms_per_session") is not None
        and candidate["false_alarms_per_session"] <= baseline["false_alarms_per_session"] + 0.5
    )
    ok = separated_recall and separated_lead and hit_ok and fa_ok
    return {
        "promote": ok,
        "recall_intervals_separated": separated_recall,
        "lead_intervals_separated": separated_lead,
        "hit_interval_not_entirely_worse": hit_ok,
        "false_alarms_close": fa_ok,
        "reason": "isolated test improved recall and lead outside the intervals" if ok else "isolated test did not clear the interval gates",
    }


def _metrics(signals, events, frame, sessions) -> dict:
    row = evaluate(signals, events, frame, sessions, "net")
    return row


def run_tune(frame) -> dict:
    spy = drop_partial_last_session(frame)
    sessions = rth_sessions(spy)
    parts = split_sessions(sessions)
    atr = five_minute_atr(spy)
    events = build_events(spy, atr)
    validation = []
    signals_by_name = {}
    for cfg in grid():
        name = config_name(cfg)
        signals = legacy_signals(spy, **cfg)
        signals_by_name[name] = signals
        row = _metrics(signals, events, spy, parts["validation"])
        row["name"] = name
        row["config"] = cfg
        validation.append(row)
    baseline = next(row for row in validation if row["name"] == config_name(DEFAULT))
    choice = select_legacy(validation, baseline)
    selected_name = choice["selected"]
    test = {
        "default": _metrics(signals_by_name[config_name(DEFAULT)], events, spy, parts["test"]),
        selected_name: _metrics(signals_by_name[selected_name], events, spy, parts["test"]),
    }
    test["default"]["name"] = config_name(DEFAULT)
    test[selected_name]["name"] = selected_name
    decision = promote_legacy(test[selected_name], test["default"])
    env = next(row["config"] for row in validation if row["name"] == selected_name)
    return {
        "sessions": {name: [day.isoformat() for day in days] for name, days in parts.items()},
        "defaults": DEFAULT,
        "validation": validation,
        "selection": choice,
        "test": {"default": test["default"], "selected": test[selected_name]},
        "promotion": decision,
        "optional_env": {
            "EXPLOSION_LEGACY_LOOKBACK": env["lookback"],
            "EXPLOSION_LEGACY_RVOL_MIN": env["rvol_min"],
            "EXPLOSION_LEGACY_MOMENTUM_PCT": env["momentum_pct"],
            "EXPLOSION_LEGACY_MIN_DISTANCE_ATR": env["min_distance_atr"],
            "applied_as_defaults": decision["promote"],
        },
        "note": "The isolated dates were already read by the context study. This grid was fixed before this run and the test was not used to choose it.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Tune legacy confirmation thresholds")
    parser.add_argument("--input", default="artifacts/explosion_1m/SPY_1m.csv.gz")
    parser.add_argument("--output", default="artifacts/explosion_1m/legacy_tune.json")
    args = parser.parse_args()
    report = run_tune(load_frame(Path(args.input)))
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    selected = report["test"]["selected"]
    base = report["test"]["default"]
    print(json.dumps({
        "selected": report["selection"]["selected"],
        "promote": report["promotion"]["promote"],
        "reason": report["promotion"]["reason"],
        "test_selected_recall": selected.get("recall_before_onset"),
        "test_default_recall": base.get("recall_before_onset"),
        "test_selected_lead": selected.get("median_lead_min"),
        "test_default_lead": base.get("median_lead_min"),
        "test_selected_hit": selected.get("forward_hit_rate"),
        "test_default_hit": base.get("forward_hit_rate"),
        "test_selected_fa": selected.get("false_alarms_per_session"),
        "test_default_fa": base.get("false_alarms_per_session"),
        "env": report["optional_env"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
