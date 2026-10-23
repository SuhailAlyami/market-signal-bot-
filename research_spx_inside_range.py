"""Evaluate the frozen inside-range hypothesis on already consumed SPX sessions.

The numeric gates are reported and cannot select a model or enable alerts.
Exit status is always NOT_READY: these dates were analyzed before this run.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from evaluate_spx_extension import inventory, load_history
from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_premove import preanchor_diagnostic
from spx_inside_range import (BASELINES, PRIMARY, VERSION, features, gap_minutes,
                              lifecycle, signal_schedule, strict_early_slots)

HEAD_END = pd.Timestamp('2026-10-22T17:30:00Z')
TAIL_START = HEAD_END


def _wick_onset(bars, events):
    config = ResearchConfig()
    for event in events:
        anchor, side = event['anchor_index'], event['direction']
        threshold = bars.Close.iloc[anchor] + side * config.onset_fraction * event['target_points']
        future = bars.iloc[anchor + 1:event['target_index'] + 1]
        touched = future.High >= threshold if side > 0 else future.Low <= threshold
        hits = np.flatnonzero(touched.to_numpy())
        event['onset_time'] = bars.index[anchor + 1 + int(hits[0])].isoformat()
        event['minutes_from_anchor_decision_to_onset'] = gap_minutes(event)
        event['strict_early_slots'] = strict_early_slots(event, bars)
    return events


def _eligible(bars, frame, start=None, end=None):
    config = ResearchConfig()
    start = pd.Timestamp(start) if start is not None else bars.index[0]
    end = pd.Timestamp(end) if end is not None else bars.index[-1] + pd.Timedelta(minutes=1)
    eligible = []
    for index in range(len(bars) - config.horizon):
        stamp = bars.index[index]
        if stamp < start or stamp >= end or not frame.valid.iloc[index]:
            continue
        if bars.index[index + config.horizon] - stamp != pd.Timedelta(minutes=config.horizon):
            continue
        eligible.append(index)
    return eligible


def _score_model(bars, frame, events, eligible, model, start=None):
    config = ResearchConfig()
    allowed = set(eligible)
    scheduled = signal_schedule(frame, model)
    if start is not None:
        scheduled = [row for row in scheduled if bars.index[row['index']] >= pd.Timestamp(start)]
    scored = [row for row in scheduled if row['index'] in allowed]
    report = dict(segment_candidates=len(scheduled), censored=len(scheduled) - len(scored),
                  strict={}, auxiliary={}, signal_matches={})
    for delay in (0, 1, 2):
        matched = [dict(row) for row in scored]
        report['strict'][str(delay)] = score_signals(
            events, matched, bars, eligible, 'rth', config, bootstrap=False,
            availability_delay_minutes=delay)
        report['auxiliary'][str(delay)] = preanchor_diagnostic(events, scored, bars, delay)
        report['signal_matches'][str(delay)] = matched
    report['numeric_gates_met'] = _numeric_gates(report['strict']['0'])
    report['qualification'] = False
    return report


def _score_lifecycle(bars, frame, events, eligible, start=None):
    """Score emitted readiness separately from later confirmation."""
    config = ResearchConfig()
    allowed = set(eligible)
    emitted = lifecycle(frame)
    if start is not None:
        emitted = [row for row in emitted if bars.index[row['index']] >= pd.Timestamp(start)]
    report = dict(states={})
    for state in ('READINESS', 'CONFIRMATION', 'CANCEL', 'EXIT'):
        rows = [dict(index=row['index'], direction=row['direction'], detected_at=row['detected_at'])
                for row in emitted if row['state'] == state]
        scored = [row for row in rows if row['index'] in allowed]
        strict = {}
        for delay in (0, 1, 2):
            strict[str(delay)] = score_signals(
                events, [dict(row) for row in scored], bars, eligible, 'rth', config,
                bootstrap=False, availability_delay_minutes=delay)
        report['states'][state] = dict(emitted=len(rows), censored=len(rows) - len(scored), strict=strict)
    report['transitions'] = emitted
    report['numeric_gates_met'] = _numeric_gates(report['states']['READINESS']['strict']['0'])
    report['qualification'] = False
    return report


def _numeric_gates(metrics):
    wilson = metrics.get('precision_wilson_95')
    lead = metrics.get('median_lead_minutes')
    per_session = metrics.get('false_alarms_per_session')
    return bool(metrics.get('signals')
                and metrics.get('precision') is not None and metrics['precision'] >= 0.50
                and wilson is not None and wilson[0] >= 0.40
                and (metrics.get('early_event_recall') or 0) >= 0.20
                and lead is not None and lead >= 1
                and per_session is not None and per_session <= 2)


def _segment(bars, name, start=None, end=None, context=None):
    """``context`` may contain earlier bars; labels and scores stay inside the slice."""
    context = bars if context is None else context
    frame = features(context)
    if context is not bars:
        # Positional indexes must refer to the frame that owns the labels.
        raise ValueError('segment_bars_must_be_the_feature_frame')
    eligible = _eligible(bars, frame, start, end)
    events = _wick_onset(bars, movement_events(bars, frame, eligible, ResearchConfig()))
    # Drop events whose target minute is outside the requested slice.
    if end is not None:
        limit = pd.Timestamp(end)
        events = [event for event in events if bars.index[event['target_index']] < limit]
    models = {model: _score_model(bars, frame, events, eligible, model, start) for model in (PRIMARY, *BASELINES)}
    return dict(name=name, start=None if start is None else pd.Timestamp(start).isoformat(),
                end=None if end is None else pd.Timestamp(end).isoformat(),
                bars=int(len(bars) if start is None else (bars.index >= pd.Timestamp(start)).sum()),
                events=len(events),
                zero_strict_early_slots=sum(not event['strict_early_slots'] for event in events),
                positive_strict_early_slots=sum(bool(event['strict_early_slots']) for event in events),
                models=models, lifecycle=_score_lifecycle(bars, frame, events, eligible, start),
                event_rows=[{key: event[key] for key in (
                    'event_id', 'direction', 'anchor_time', 'onset_time', 'target_time',
                    'minutes_from_anchor_decision_to_onset', 'strict_early_slots')}
                    for event in events])


def _audit(bars, frame):
    full = {model: signal_schedule(frame, model) for model in (PRIMARY, *BASELINES)}
    prefix, poison = [], []
    for count in (31, 120, 240, 390):
        if count > len(bars):
            continue
        partial = features(bars.iloc[:count])
        prefix.append({model: signal_schedule(partial, model) == [row for row in full[model] if row['index'] < count]
                       for model in full})
    for count in (120, 240):
        if count >= len(bars):
            continue
        changed = bars.copy()
        changed.iloc[count:] = changed.iloc[count:] + 1000
        changed.attrs.update(symbol='SPX', security_type='IND')
        future = features(changed)
        poison.append({model: [row for row in signal_schedule(future, model) if row['index'] < count]
                       == [row for row in full[model] if row['index'] < count] for model in full})
    rows = prefix + poison
    return dict(prefix=prefix, future_poison=poison,
                passed=all(all(item.values()) for item in rows))


def run(source, output, protocol_commit):
    bars, payload, digest, excluded = load_history(source)
    coverage = inventory(bars)
    labels = bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    by_day = {day: group.copy() for day, group in bars.groupby(labels, sort=True)}
    for group in by_day.values():
        group.attrs.update(symbol='SPX', security_type='IND')
    october22 = by_day['2026-10-22']
    head = october22.loc[october22.index < HEAD_END].copy()
    head.attrs.update(symbol='SPX', security_type='IND')
    if len(head) != 240 or head.index[-1] != pd.Timestamp('2026-10-22T17:29:00Z'):
        raise ValueError('consumed_head_boundary_changed')
    segments = [
        _segment(head, 'oct22_consumed_head'),
        _segment(october22, 'oct22_consumed_tail', start=TAIL_START),
        _segment(by_day['2026-10-21'], 'oct21_backward_transfer'),
    ]
    if '2026-10-20' in by_day:
        segments.append(_segment(by_day['2026-10-20'], 'oct20_partial_inventory'))
    head_row, tail_row, transfer_row = segments[:3]
    if (head_row['events'], tail_row['events'], transfer_row['events']) != (16, 12, 22):
        raise ValueError('event_universe_drift')
    if head_row['zero_strict_early_slots'] != 9:
        raise ValueError('strict_early_geometry_drift')
    result = dict(
        mode='CONSUMED_SESSION_INSIDE_RANGE_DIAGNOSTIC',
        rule_version=VERSION, protocol_commit=protocol_commit,
        input_sha256=digest, provider_chart_end=payload['history']['chart_end'],
        received_at=payload['received_at'], excluded_partial_bars=excluded,
        contract_id=payload['contract']['underlying_contract_id'],
        decision_clock='provider bar start plus one minute; receipt time is not a decision timestamp',
        coverage=coverage, segments=segments,
        causality=_audit(october22, features(october22)),
        model_selected=None, holdout_opened=False, independent_validation=False,
        accepted=False, readiness='NOT_READY', notifications_enabled=False,
        orders_enabled=False, live_feed_verified=False,
        limitations=[
            'Oct20, Oct21 and Oct22 were already inspected before this hypothesis.',
            'No 12/4/4 untouched session split exists in this capture.',
            'Numeric gates are disclosed and are not allowed to qualify the rule.',
            'Auxiliary pre-anchor matches are not acceptance evidence.',
            'Simulated 0/1/2 minute delays are not measured provider latency.',
            'No option quote, fill, order or Telegram delivery is produced.',
        ])
    Path(output).write_text(json.dumps(result, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    return result


def _print(result):
    for segment in result['segments']:
        print(segment['name'], 'events', segment['events'],
              'zero_slots', segment['zero_strict_early_slots'])
        for name, row in segment['models'].items():
            metrics = row['strict']['0']
            print(' ', name, {key: metrics[key] for key in (
                'signals', 'matched_events', 'early_matched_events', 'false_alarms',
                'median_lead_minutes', 'early_event_recall', 'false_alarms_per_session')},
                  'gates', row['numeric_gates_met'])
        readiness = segment['lifecycle']['states']['READINESS']['strict']['0']
        confirmation = segment['lifecycle']['states']['CONFIRMATION']['strict']['0']
        print('  lifecycle_readiness', readiness['early_matched_events'], '/', readiness['signals'],
              'confirm_early', confirmation['early_matched_events'], '/', confirmation['signals'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    _print(run(args.input, args.output, args.protocol_commit))
    raise SystemExit(2)
