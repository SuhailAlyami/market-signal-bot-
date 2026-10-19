"""Causal one-minute event research. No orders, option quotes, or profitability claims.

Bar timestamps denote the START of a completed minute. Features use only that
minute and its past. Labels are a separate forward-only operation. The last
chronological partition is never consulted during parameter selection.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


NY = ZoneInfo("America/New_York")
OHLCV = ["Open", "High", "Low", "Close", "Volume"]
DEFAULT_PARAMS = {"proximity": 0.20, "rvol": 1.2, "impulse": 1.3,
                  "contraction": 0.65, "trend": 0.0}
METHODS = ("pre_level", "contraction_expansion", "acceleration",
           "failed_breakout", "multiframe_rvol")
BASELINES = ("no_signal", "trend_persistence", "breakout")


@dataclass(frozen=True)
class ResearchConfig:
    horizon: int = 10
    target_pct: float = 0.0006
    target_atr: float = 2.0
    onset_fraction: float = 0.25
    cooldown: int = 10
    bootstrap_samples: int = 500
    seed: int = 16


def validate_bars(bars: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("timezone-aware 1m bar start timestamps required")
    if any(column not in bars for column in OHLCV):
        raise ValueError("Open, High, Low, Close, Volume required")
    if not bars.index.is_unique or not bars.index.is_monotonic_increasing:
        raise ValueError("timestamps must be unique and increasing; do not silently repair data")
    if not (bars.index == bars.index.floor("min")).all():
        raise ValueError("timestamps must be aligned to one-minute starts")
    data = bars[OHLCV].astype(float).copy()
    data.index = data.index.tz_convert("UTC")
    return data


def _session_labels(index: pd.DatetimeIndex, session: str = "all") -> pd.Index:
    local = index.tz_convert(NY)
    dates = local.tz_localize(None).normalize()
    if session == "all":
        # The ES/NQ trading day starts at 18:00 New York on the prior date.
        dates = dates + pd.to_timedelta((local.hour >= 18).astype(int), unit="D")
    return pd.Index(dates.strftime("%Y-%m-%d"), name="session")


def feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """Compute causal features once; retained gaps invalidate recent windows."""
    data = validate_bars(bars)
    result = pd.DataFrame(index=data.index)
    good = (np.isfinite(data).all(axis=1) & (data.Volume > 0) & (data.Low > 0)
            & (data.High >= data[["Open", "Close", "Low"]].max(axis=1))
            & (data.Low <= data[["Open", "Close"]].min(axis=1)))
    close = data.Close
    prev = close.shift(1)
    tr = pd.concat([data.High-data.Low, (data.High-prev).abs(),
                    (data.Low-prev).abs()], axis=1).max(axis=1)
    atr = tr.shift(1).rolling(20, min_periods=20).mean()
    result["close"] = close
    result["atr"] = atr
    result["range_high"] = data.High.shift(1).rolling(20).max()
    result["range_low"] = data.Low.shift(1).rolling(20).min()
    result["span"] = result.range_high-result.range_low
    result["rvol"] = data.Volume/data.Volume.shift(1).rolling(20).median()
    result["move"] = (close-data.Open)/atr
    result["trend_5"] = (close-close.shift(5))/atr
    result["trend_15"] = (close-close.shift(15))/atr
    result["acceleration"] = ((close-close.shift(3))-(close.shift(3)-close.shift(6)))/atr
    result["contraction"] = ((data.High.shift(1).rolling(5).max()
                              - data.Low.shift(1).rolling(5).min())/result.span)
    result["high"] = data.High
    result["low"] = data.Low
    labels = _session_labels(data.index)
    extrema = data.where(good, np.nan).groupby(labels, sort=True).agg({"High": "max", "Low": "min"})
    # A missing/invalid/partial source session cannot establish its true levels.
    for label, group in data.groupby(labels, sort=True):
        day = pd.Timestamp(label, tz=NY)
        start = (day-pd.DateOffset(days=1)).replace(hour=18)
        end = day.replace(hour=17)
        complete = (len(group) == int((end-start).total_seconds()/60)
                    and group.index[0] == start and group.index[-1] == end-pd.Timedelta(minutes=1)
                    and bool(good.loc[group.index].all()))
        if not complete:
            extrema.loc[label] = np.nan
    extrema = extrema.shift(1)
    result["prior_high"] = labels.map(extrema.High).to_numpy()
    result["prior_low"] = labels.map(extrema.Low).to_numpy()
    local = data.index.tz_convert(NY)
    dates = pd.Index(local.date.astype(str))
    day_extrema = data.where(good, np.nan).groupby(dates, sort=True).agg({"High": "max", "Low": "min"})
    for label, group in data.groupby(dates, sort=True):
        day = pd.Timestamp(label, tz=NY)
        # NY calendar day contains the normal 17:00-18:00 futures maintenance.
        expected = 1380
        if not (len(group) == expected and group.index[0] == day
                and group.index[-1] == (day+pd.DateOffset(days=1))-pd.Timedelta(minutes=1)
                and bool(good.loc[group.index].all())):
            day_extrema.loc[label] = np.nan
    day_extrema = day_extrema.shift(1)
    result["prior_day_high"] = dates.map(day_extrema.High).to_numpy()
    result["prior_day_low"] = dates.map(day_extrema.Low).to_numpy()
    minute = local.hour*60+local.minute
    opening = data.loc[(minute >= 570) & (minute < 585) & good.to_numpy()]
    opening_dates = pd.Index(opening.index.tz_convert(NY).date.astype(str))
    opening_extrema = opening.groupby(opening_dates).agg({"High": "max", "Low": "min", "Volume": "count"})
    # An opening range is known only after all 15 completed minute bars exist.
    opening_extrema = opening_extrema.loc[opening_extrema.Volume == 15]
    result["opening_high"] = dates.map(opening_extrema.High).to_numpy()
    result["opening_low"] = dates.map(opening_extrema.Low).to_numpy()
    result.loc[minute < 585, ["opening_high", "opening_low"]] = np.nan
    upper = result[["range_high", "prior_high", "prior_day_high", "opening_high"]]
    lower = result[["range_low", "prior_low", "prior_day_low", "opening_low"]]
    result["level_high"] = upper.where(upper.ge(close, axis=0)).min(axis=1)
    result["level_low"] = lower.where(lower.le(close, axis=0)).max(axis=1)
    result["near_high"] = (result.level_high-close)/atr
    result["near_low"] = (close-result.level_low)/atr
    contiguous = data.index.to_series().diff().eq(pd.Timedelta(minutes=1))
    result["valid"] = (good.rolling(31).sum().eq(31)
                       & contiguous.rolling(30).sum().eq(30)
                       & atr.gt(0) & result.span.gt(0))
    return result


def causal_features(bars: pd.DataFrame, i: int) -> dict | None:
    """Runtime API: never inspect bars later than i, even if supplied."""
    if i < 30 or i >= len(bars):
        return None
    row = feature_frame(bars.iloc[:i+1]).iloc[-1]
    return row.to_dict() if bool(row.valid) else None


def candidate_signal(features: dict | pd.Series | None, method: str,
                     params: dict | None = None) -> int:
    """Return underlying direction only. SETUPs remain research hypotheses."""
    if features is None or not features.get("valid", True):
        return 0
    p = {**DEFAULT_PARAMS, **(params or {})}
    f = features
    if method == "no_signal":
        return 0
    if method == "trend_persistence":
        return 1 if f["trend_5"] > 0 else -1 if f["trend_5"] < 0 else 0
    if method == "breakout":
        return (1 if f["close"] > f["range_high"] and f["rvol"] >= p["rvol"]
                else -1 if f["close"] < f["range_low"] and f["rvol"] >= p["rvol"] else 0)
    uptrend = f["trend_5"] > p["trend"] and f["trend_15"] >= 0
    downtrend = f["trend_5"] < -p["trend"] and f["trend_15"] <= 0
    upnear = 0 <= f["near_high"] <= p["proximity"]
    downnear = 0 <= f["near_low"] <= p["proximity"]
    liquid = f["rvol"] >= p["rvol"]
    if method == "pre_level":
        up = upnear and f["move"] > 0 and uptrend and liquid
        down = downnear and f["move"] < 0 and downtrend and liquid
    elif method == "contraction_expansion":
        tight = f["contraction"] <= p["contraction"]
        up = tight and upnear and f["move"] > 0 and uptrend and liquid
        down = tight and downnear and f["move"] < 0 and downtrend and liquid
    elif method == "acceleration":
        up = f["acceleration"] >= p["impulse"] and f["move"] > 0 and uptrend and liquid
        down = f["acceleration"] <= -p["impulse"] and f["move"] < 0 and downtrend and liquid
    elif method == "failed_breakout":
        up = f["low"] < f["range_low"] < f["close"] and f["move"] > 0 and liquid
        down = f["high"] > f["range_high"] > f["close"] and f["move"] < 0 and liquid
    elif method == "multiframe_rvol":
        up = uptrend and f["move"] >= p["impulse"] and liquid
        down = downtrend and f["move"] <= -p["impulse"] and liquid
    else:
        raise ValueError(f"unknown method: {method}")
    return 1 if up and not down else -1 if down and not up else 0


def session_inventory(bars: pd.DataFrame, session: str, as_of: pd.Timestamp) -> list[dict]:
    local = bars.index.tz_convert(NY)
    minutes = local.hour*60+local.minute
    if session == "rth":
        mask = (minutes >= 570) & (minutes < 960) & (local.dayofweek < 5)
    else:
        mask = np.ones(len(bars), dtype=bool)
    observed = bars.loc[mask]
    labels = _session_labels(observed.index, session)
    inventory = []
    for label, group in observed.groupby(labels):
        day = pd.Timestamp(label, tz=NY)
        # Set wall-clock hours rather than adding elapsed hours across DST.
        start = day.replace(hour=9, minute=30) if session == "rth" else (day-pd.DateOffset(days=1)).replace(hour=18)
        end = day.replace(hour=16 if session == "rth" else 17)
        complete = (as_of >= end and group.index[0] <= start+pd.Timedelta(minutes=1)
                    and group.index[-1] >= end-pd.Timedelta(minutes=2)
                    and day.dayofweek < 5)
        inventory.append({"session": label, "rows": len(group), "first": group.index[0].isoformat(),
                          "last": group.index[-1].isoformat(), "complete": bool(complete),
                          "reason": "complete_boundaries" if complete else "partial_or_current_or_nontrading_session"})
    return inventory


def chronological_splits(bars: pd.DataFrame, session: str, as_of: pd.Timestamp,
                         horizon: int) -> tuple[dict[str, list[int]], list[dict]]:
    inventory = session_inventory(bars, session, as_of)
    days = [x["session"] for x in inventory if x["complete"]]
    if len(days) < 4:
        raise ValueError(f"need at least four complete sessions; observed {len(days)}")
    train_end = max(2, int(len(days)*0.5))
    validation_end = max(train_end+1, int(len(days)*0.75))
    validation_end = min(validation_end, len(days)-1)
    phase_days = {"train": days[:train_end], "validation": days[train_end:validation_end],
                  "test": days[validation_end:]}
    labels = _session_labels(bars.index, session)
    local = bars.index.tz_convert(NY)
    in_hours = ((local.hour*60+local.minute >= 570) & (local.hour*60+local.minute < 960)
                if session == "rth" else np.ones(len(bars), dtype=bool))
    splits = {}
    for phase, selected in phase_days.items():
        indices = np.flatnonzero(labels.isin(selected) & in_hours).tolist()
        # Both boundary sides are embargoed; no forward label crosses a phase.
        splits[phase] = indices[horizon:-horizon] if len(indices) > 2*horizon else []
    return splits, inventory


def eligible_indices(bars: pd.DataFrame, features: pd.DataFrame, indices: list[int],
                     config: ResearchConfig) -> list[int]:
    allowed = set(indices)
    valid = features.valid.to_numpy()
    data = bars[OHLCV].to_numpy()
    timestamps = bars.index.as_unit("ns").asi8
    eligible = []
    for i in indices:
        end = i+config.horizon
        if end >= len(bars) or end not in allowed or not valid[i]:
            continue
        future = data[i+1:end+1]
        if (timestamps[end]-timestamps[i] != config.horizon*60_000_000_000
                or not np.isfinite(future).all() or (future[:, 4] <= 0).any()
                or (future[:, 2] <= 0).any()
                or (future[:, 1] < np.maximum(future[:, 0], future[:, 3])).any()
                or (future[:, 2] > np.minimum(future[:, 0], future[:, 3])).any()):
            continue
        eligible.append(i)
    return eligible


def movement_events(bars: pd.DataFrame, features: pd.DataFrame, indices: list[int],
                    config: ResearchConfig) -> list[dict]:
    """Independent, non-overlapping forward labels; ambiguous same-bar paths excluded.

    At each eligible anchor, seek the first +/- max(0.06%, 2 prior ATR) high/low
    touch in 10 minutes. Onset is the first completed close reaching 25% of that
    target in the eventual direction. Windows are greedily non-overlapping.
    """
    events = []
    next_anchor = -1
    for i in indices:
        if i < next_anchor:
            continue
        entry = float(bars.Close.iloc[i])
        target = max(entry*config.target_pct, float(features.atr.iloc[i])*config.target_atr)
        future = bars.iloc[i+1:i+config.horizon+1]
        up = np.flatnonzero(future.High.to_numpy() >= entry+target)
        down = np.flatnonzero(future.Low.to_numpy() <= entry-target)
        u = int(up[0]) if len(up) else config.horizon+1
        d = int(down[0]) if len(down) else config.horizon+1
        if u == d:  # Neither target or unknowable intrabar ordering.
            continue
        direction = 1 if u < d else -1
        hit = min(u, d)
        onset = np.flatnonzero(direction*(future.Close.to_numpy()[:hit+1]-entry) >= config.onset_fraction*target)
        if not len(onset):
            continue
        events.append({"event_id": len(events), "anchor_index": i,
                       "onset_index": i+1+int(onset[0]), "target_index": i+1+hit,
                       "end_index": i+config.horizon, "direction": direction,
                       "target_points": target, "anchor_time": bars.index[i].isoformat(),
                       "onset_time": (bars.index[i+1+int(onset[0])]+pd.Timedelta(minutes=1)).isoformat(),
                       "target_time": (bars.index[i+1+hit]+pd.Timedelta(minutes=1)).isoformat()})
        next_anchor = i+config.horizon+1
    return events


def signals_for(features: pd.DataFrame, indices: list[int], method: str, params: dict,
                config: ResearchConfig) -> list[dict]:
    signals = []
    next_signal = -1
    for i in indices:
        if i < next_signal:
            continue
        direction = candidate_signal(features.iloc[i], method, params)
        if direction:
            signals.append({"index": i, "direction": direction,
                            "bar_time": features.index[i].isoformat(),
                            "detected_at": (features.index[i]+pd.Timedelta(minutes=1)).isoformat()})
            next_signal = i+config.cooldown
    return signals


def wilson(successes: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    p = successes/total
    denominator = 1+z*z/total
    midpoint = (p+z*z/(2*total))/denominator
    half = z*math.sqrt(p*(1-p)/total+z*z/(4*total*total))/denominator
    return [max(0., midpoint-half), min(1., midpoint+half)]


def score_signals(events: list[dict], signals: list[dict], bars: pd.DataFrame,
                  indices: list[int], session: str, config: ResearchConfig,
                  bootstrap: bool = True, availability_delay_minutes: int = 0,
                  _labels: pd.Index | None = None) -> dict:
    labels = _session_labels(bars.index, session) if _labels is None else _labels
    sessions = sorted(set(labels[indices]))
    counts = {day: {"events": 0, "signals": 0, "matched": 0, "early": 0,
                    "leads": []} for day in sessions}
    for event in events:
        counts[labels[event["anchor_index"]]]["events"] += 1
    matched_events = set()
    leads = []
    for signal in signals:
        day = labels[signal["index"]]
        counts[day]["signals"] += 1
        signal["event_id"] = None
        signal["lead_minutes"] = None
        delivery = pd.Timestamp(signal["detected_at"])+pd.Timedelta(minutes=availability_delay_minutes)
        for event in events:
            if (event["event_id"] not in matched_events
                    and event["direction"] == signal["direction"]
                    and event["anchor_index"] <= signal["index"] < event["target_index"]
                    and event["target_index"] <= signal["index"]+config.horizon
                    and delivery <= bars.index[event["target_index"]]):
                lead = (pd.Timestamp(event["onset_time"])-delivery).total_seconds()/60
                matched_events.add(event["event_id"])
                signal["event_id"] = event["event_id"]
                signal["lead_minutes"] = lead
                leads.append(lead)
                counts[day]["matched"] += 1
                counts[day]["early"] += int(lead > 0)
                counts[day]["leads"].append(lead)
                break
    hits = len(matched_events)
    early = sum(x > 0 for x in leads)
    result = {"availability_delay_minutes": availability_delay_minutes,
              "sessions": len(sessions), "eligible_minutes": len(indices),
              "events": len(events), "signals": len(signals), "matched_events": hits,
              "precision": hits/len(signals) if signals else None,
              "recall": hits/len(events) if events else None,
              "early_precision": early/len(signals) if signals else None,
              "early_event_recall": early/len(events) if events else None,
              "median_lead_minutes": float(np.median(leads)) if leads else None,
              "early_matched_events": early, "false_alarms": len(signals)-hits,
              "early_false_alarms": len(signals)-early,
              "false_alarms_per_session": (len(signals)-hits)/len(sessions) if sessions else None,
              "missed_events": len(events)-hits,
              "precision_wilson_95": wilson(hits, len(signals)),
              "recall_wilson_95": wilson(hits, len(events)),
              "early_precision_wilson_95": wilson(early, len(signals)),
              "early_recall_wilson_95": wilson(early, len(events)),
              "session_counts": counts}
    if bootstrap and sessions:
        rng = np.random.default_rng(config.seed)
        estimates = {key: [] for key in ("precision", "recall", "early_precision", "early_event_recall", "false_alarms_per_session", "median_lead_minutes")}
        for _ in range(config.bootstrap_samples):
            sampled = [counts[sessions[x]] for x in rng.integers(0, len(sessions), len(sessions))]
            n = sum(x["signals"] for x in sampled)
            e = sum(x["events"] for x in sampled)
            h = sum(x["matched"] for x in sampled)
            early_n = sum(x["early"] for x in sampled)
            sampled_leads = [lead for row in sampled for lead in row["leads"]]
            if n:
                estimates["precision"].append(h/n)
                estimates["early_precision"].append(early_n/n)
            if e:
                estimates["recall"].append(h/e)
                estimates["early_event_recall"].append(early_n/e)
            estimates["false_alarms_per_session"].append((n-h)/len(sessions))
            if sampled_leads:
                estimates["median_lead_minutes"].append(float(np.median(sampled_leads)))
        result["session_bootstrap_95"] = {key: [float(v) for v in np.quantile(values, [.025, .975])]
                                          if values else None for key, values in estimates.items()}
    return result


def parameter_grid() -> list[dict]:
    """Declared before data inspection; modest grid, no holdout-driven changes."""
    grid = []
    for method in METHODS:
        for q in (0.50, 0.75):
            for variant in (0, 1):
                params = {**DEFAULT_PARAMS, "rvol_quantile": q}
                if method in ("pre_level", "contraction_expansion"):
                    params["proximity"] = (0.2, 0.6)[variant]
                    params["contraction"] = (0.45, 0.65)[variant]
                else:
                    params["impulse"] = (1.2, 1.8)[variant]
                grid.append({"id": f"{method}_q{q}_v{variant}", "method": method, "params": params})
    return grid


def fit_parameters(features: pd.DataFrame, train_indices: list[int], params: dict) -> dict:
    """The relative-volume cutoff is fitted only to the named training prefix."""
    result = dict(params)
    q = result.pop("rvol_quantile", None)
    if q is not None:
        training = features.iloc[train_indices]
        values = training.loc[training.valid, "rvol"].replace([np.inf, -np.inf], np.nan).dropna()
        result["rvol"] = max(1.0, float(values.quantile(q))) if len(values) else 1.2
    return result


def selection_score(metrics: dict) -> float:
    # Predetermined EARLY F1 rewards warnings before onset, not late triggers.
    p, r = metrics["early_precision"] or 0., metrics["early_event_recall"] or 0.
    return 2*p*r/(p+r) if p+r else 0.


def _evaluation_context(bars, features, indices, session, config):
    eligible = eligible_indices(bars, features, indices, config)
    events = movement_events(bars, features, eligible, config)
    # Scheduling is causal: even a signal whose future later proves missing
    # consumes cooldown. Only its outcome is censored after detection.
    causal = [i for i in indices if features.valid.iloc[i]]
    return {"eligible": eligible, "events": events, "causal": causal,
            "labels": _session_labels(bars.index, session)}


def _evaluate(bars, features, indices, method, params, session, config, bootstrap=False,
              _context=None):
    context = _context or _evaluation_context(bars, features, indices, session, config)
    eligible, events, causal = context["eligible"], context["events"], context["causal"]
    signals = signals_for(features, causal, method, params, config)
    observable = set(eligible)
    for signal in signals:
        signal["outcome_observable"] = signal["index"] in observable
        signal["censored_reason"] = None if signal["outcome_observable"] else "future_horizon_missing_invalid_or_outside_partition"
    scored = [signal for signal in signals if signal["outcome_observable"]]
    metrics = score_signals(events, scored, bars, eligible, session, config, bootstrap,
                            _labels=context["labels"])
    metrics["candidate_signals_total"] = len(signals)
    metrics["censored_signals"] = len(signals)-len(scored)
    return metrics, events, signals


def benchmark(bars: pd.DataFrame, symbol: str, session: str = "all",
              as_of: pd.Timestamp | None = None, config: ResearchConfig | None = None) -> tuple[dict, dict[str, pd.DataFrame]]:
    config = config or ResearchConfig()
    if config.horizon < 1 or config.cooldown < 1 or not 0 < config.onset_fraction <= 1:
        raise ValueError("positive horizon/cooldown and onset_fraction in (0,1] required")
    data = validate_bars(bars)
    as_of = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if as_of.tz is None:
        raise ValueError("timezone-aware as_of required")
    # Future/incomplete bars do not enter features, partitions or outcomes.
    incomplete = int(((data.index+pd.Timedelta(minutes=1)) > as_of).sum())
    data = data.loc[(data.index+pd.Timedelta(minutes=1)) <= as_of]
    features = feature_frame(data)
    splits, inventory = chronological_splits(data, session, as_of, config.horizon)
    labels = _session_labels(data.index, session)
    contexts = {}

    def evaluate(indices, method, params, bootstrap=False):
        # Outcomes and observable windows are independent of the candidate.
        key = tuple(indices)
        if key not in contexts:
            contexts[key] = _evaluation_context(data, features, indices, session, config)
        return _evaluate(data, features, indices, method, params, session, config,
                         bootstrap, _context=contexts[key])

    training_days = sorted(set(labels[splits["train"]]))
    grid = parameter_grid()
    search_results = []
    # Expanding walk-forward folds are wholly INSIDE train. No validation/test
    # values fit a threshold or contribute to this first-stage candidate search.
    for candidate in grid:
        fold_scores = []
        fold_rows = []
        for offset in range(1, len(training_days)):
            past_days = set(training_days[:offset])
            next_day = training_days[offset]
            past = [i for i in splits["train"] if labels[i] in past_days]
            next_indices = [i for i in splits["train"] if labels[i] == next_day]
            past = past[:-config.horizon]
            next_indices = next_indices[config.horizon:-config.horizon]
            fitted = fit_parameters(features, past, candidate["params"])
            metrics, _, _ = evaluate(next_indices, candidate["method"], fitted)
            fold_scores.append(selection_score(metrics))
            fold_rows.append({"train_sessions": sorted(past_days), "validation_session": next_day,
                              "fitted_params": fitted, "metrics": metrics})
        fitted = fit_parameters(features, splits["train"], candidate["params"])
        train_metrics, _, _ = evaluate(splits["train"], candidate["method"], fitted)
        search_results.append({**candidate, "fitted_params": fitted,
                               "train_walk_forward_f1": float(np.mean(fold_scores)) if fold_scores else 0.,
                               "train_metrics": train_metrics, "train_walk_forward_folds": fold_rows})
    shortlist = []
    for method in METHODS:
        ranked = sorted([x for x in search_results if x["method"] == method],
                        key=lambda x: (-x["train_walk_forward_f1"], -selection_score(x["train_metrics"]), x["id"]))
        shortlist.extend(ranked[:2])
    validation = []
    for candidate in shortlist:
        metrics, _, _ = evaluate(splits["validation"], candidate["method"], candidate["fitted_params"])
        validation.append({"id": candidate["id"], "method": candidate["method"],
                           "params": candidate["fitted_params"], "metrics": metrics})
    selected = sorted(validation, key=lambda x: (-selection_score(x["metrics"]), x["id"]))[0]
    # Freeze here: every following test evaluation is publication, never choice.
    results = {}
    artifacts = {}
    delay_sensitivity = {}
    for phase, indices in splits.items():
        metrics, events, signals = evaluate(indices, selected["method"], selected["params"], True)
        baseline_results = {}
        for method in BASELINES:
            baseline_metrics, _, baseline_signals = evaluate(indices, method, {"rvol": 1.3}, True)
            baseline_results[method] = baseline_metrics
            artifacts[f"{phase}_baseline_{method}_signals"] = pd.DataFrame(baseline_signals)
        results[phase] = {"selected": metrics, "baselines": baseline_results}
        artifacts[f"{phase}_events"] = pd.DataFrame(events)
        artifacts[f"{phase}_signals"] = pd.DataFrame(signals)
        if phase == "test":
            eligible = eligible_indices(data, features, indices, config)
            for delay in (0, 5, 10, 15):
                delayed = score_signals(events, [dict(x) for x in signals if x["outcome_observable"]],
                                        data, eligible, session, config, True, delay, _labels=labels)
                delayed_baselines = {}
                for baseline_method in BASELINES:
                    _, _, baseline_signals = evaluate(indices, baseline_method, {"rvol": 1.3})
                    delayed_baselines[baseline_method] = score_signals(
                        events, [dict(x) for x in baseline_signals if x["outcome_observable"]],
                        data, eligible, session, config, True, delay, _labels=labels)
                delay_sensitivity[str(delay)] = {"selected": delayed, "baselines": delayed_baselines}
    split_rows = []
    for phase, indices in splits.items():
        split_rows.extend({"timestamp": data.index[i].isoformat(), "phase": phase,
                           "session": labels[i]} for i in indices)
    artifacts["splits"] = pd.DataFrame(split_rows)
    test = results["test"]["selected"]
    enough_sessions = len([x for x in inventory if x["complete"]]) >= 20 and test["sessions"] >= 5
    # Finite short samples cannot authorize live alerts; a future independent
    # evaluation and verified timely feed are required even after good results.
    readiness_reasons = ["No verified timely feed or live option chain; research-only underlying study.",
                         "No independent forward shadow sample yet; alerts must remain off."]
    if not enough_sessions:
        readiness_reasons.append("Insufficient independent sessions (requires >=20 complete and >=5 holdout sessions).")
    baseline = results["test"]["baselines"]["breakout"]
    if selection_score(test) <= selection_score(baseline):
        readiness_reasons.append("Selected detector did not improve holdout early-event F1 over completed-breakout baseline.")
    if test["median_lead_minutes"] is None or test["median_lead_minutes"] <= 0:
        readiness_reasons.append("Positive median early lead was not demonstrated.")
    report = {"symbol": symbol, "session": session, "status": "NOT READY",
              "readiness_reasons": readiness_reasons, "config": config.__dict__,
              "as_of": as_of.isoformat(), "sample_first": data.index[0].isoformat(),
              "sample_last": data.index[-1].isoformat(), "rows": len(data),
              "excluded_incomplete_rows": incomplete, "session_inventory": inventory,
              "selected": selected, "parameter_search_train_only": search_results,
              "validation_shortlist": validation, "results": results,
              "holdout_availability_delay_sensitivity": delay_sensitivity,
              "data_availability": {
                  "invalid_ohlcv_rows": int((~np.isfinite(data).all(axis=1) | (data.Volume <= 0)
                                             | (data.Low <= 0) | (data.High < data[["Open", "Close", "Low"]].max(axis=1))
                                             | (data.Low > data[["Open", "Close"]].min(axis=1))).sum()),
                  "gaps_over_one_minute": int(data.index.to_series().diff().gt(pd.Timedelta(minutes=1)).sum()),
                  "causal_feature_eligible_rows": int(features.valid.sum()),
                  "censoring": "Candidate schedule/cooldown uses past only. Signals whose future horizon is unobservable are retained and censored from precision denominator; censored counts are reported. No inferred outcomes for outages.",
                  "latency": "Sensitivity adds 0/5/10/15 minutes to theoretical completed-bar decision time; delivery must precede target bar start. Does not measure historical publication timestamps or intraminute feed availability."},
              "protocol": {
                  "timestamps": "UTC bar start; decisions and onset at completed bar close (+1 minute).",
                  "split": "First 50% complete sessions train, next 25% validation, final 25% untouched test; horizon embargo at both phase boundaries.",
                  "walk_forward": "Expanding earlier train sessions fit rvol quantile; next train session ranks candidates. Top two per method shortlisted by train only, validation EARLY event F1 selects one. Parameters remain fitted on train; no refit on validation/test.",
                  "event": "Greedy non-overlapping forward windows: first +/- max(target_pct*close,target_atr*prior20ATR) touch within horizon; same-bar two-sided hits excluded. Onset is first completed close reaching onset_fraction of target. Windows skipped after a labeled event through anchor+horizon.",
                  "matching": "One direction-matched signal per independent event between anchor and target; completed decision/delayed delivery must precede target bar start, target within signal horizon. Earliest signal matches first eligible event. Cooldown applies before future-outcome censoring. Post-onset/pre-target matches have nonpositive lead and do not count in early precision/recall or selection objective.",
                  "confidence": "Wilson binomial 95% plus deterministic session-block bootstrap percentile 95%; short samples and few sessions make intervals unreliable; bootstrap is descriptive, not proof of edge.",
                  "costs": "Classification only: no execution/P&L, fills, commissions, spread or slippage simulated. No claim these detections are profitable after costs, premium decay or execution latency."},
              "limitations": [
                  "Yahoo historical one-minute bars may be delayed, revised, missing or contract-roll affected. Acquisition time minus last bar time is age, not measured publication latency.",
                  "Only fully bounded observed sessions are used; opening-range feature requires 15 bars. Holidays are inferred from observed data, not modeled as complete regular sessions.",
                  "Zero-volume/malformed bars, gaps, incomplete minutes and their recent/future windows are excluded; excluded minutes can hide unobservable missed events.",
                  "Event definition and chronological partitions are predeclared engineering choices, not externally validated market truth. Greedy non-overlap omits overlapping opportunities.",
                  "Many hypotheses are compared in development. Published holdout baselines are descriptive; do not tune or select another detector after inspecting test.",
                  "Bootstrap treats sessions as blocks but sessions can remain correlated. Wilson intervals assume independent events; neither establishes statistical significance.",
                  "Completed one-minute underlying bars cannot establish pre-inflation SPX 0DTE option execution or tick-level early prediction."]}
    return report, artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="No-orders chronological event research from retained 1m OHLCV")
    parser.add_argument("--input", required=True, help="CSV with first column timezone-aware bar start timestamp")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--session", choices=("all", "rth", "both"), default="both")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of", help="Timezone-aware acquisition timestamp; defaults to actual UTC now")
    args = parser.parse_args()
    raw = Path(args.input).read_bytes()
    bars = pd.read_csv(args.input, index_col=0, parse_dates=True)
    bars.index = pd.to_datetime(bars.index, utc=True) if isinstance(bars.index, pd.DatetimeIndex) and bars.index.tz is not None else bars.index
    as_of = pd.Timestamp(args.as_of) if args.as_of else pd.Timestamp.now(tz="UTC")
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    for session in (("all", "rth") if args.session == "both" else (args.session,)):
        try:
            report, artifacts = benchmark(bars, args.symbol, session, as_of)
            report["input"] = {"path": args.input, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
            for name, frame in artifacts.items():
                frame.to_csv(output/f"{session}_{name}.csv", index=False)
        except ValueError as error:
            report = {"symbol": args.symbol, "session": session, "status": "NOT READY",
                      "error": str(error), "input_sha256": hashlib.sha256(raw).hexdigest(),
                      "as_of": as_of.isoformat(), "no_result_fabricated": True}
        (output/f"{session}_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(json.dumps({"symbol": args.symbol, "session": session, "status": report["status"],
                          "holdout": report.get("results", {}).get("test"), "error": report.get("error")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
