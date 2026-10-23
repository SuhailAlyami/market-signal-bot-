"""Frozen chronological SPX price-only study of native Gateway session captures.

Integrity checks may read all files. Holdout features, labels and metrics are
computed only after training selection and the fixed validation gate pass.
No live market data, alerts, options, orders or strategy deployment.
"""
import argparse
from datetime import date
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from collect_spx_sessions import request_end, validate_session
from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_premove import MODELS, features, preanchor_diagnostic, signal_schedule

PROTOCOL_COMMIT = '355c2d8d728b119c4768c6767051132fe7afd8d6'
EXCLUDED_FROM = '2026-10-22'
HYPOTHESES = MODELS[:4]
BASELINES = ('sweep_reclaim', 'original_candidate', 'no_signal')
CAPTURE_FAILURES = {
    'native_gateway_capture_required', 'native_spx_identity_required',
    'missing_session_inventory', 'invalid_session_date',
    'session_dates_not_unique_and_ordered', 'consumed_or_later_session_excluded',
    'non_trading_day', 'raw_hash_mismatch', 'mixed_contracts',
    'unexpected_history_request', 'session_not_complete_at_receipt',
    'missing_provider_bounds', 'incomplete_capture',
    'need_at_least_20_independent_full_sessions', 'insufficient_split_sizes',
    'unordered_bars', 'conflicting_duplicate', 'invalid_ohlc_or_timestamp',
    'previous_holdout_in_training_or_validation',
}


def load_capture(directory):
    """Recompute coverage from hashed raw files, never trust validated summaries."""
    directory = Path(directory)
    manifest_bytes = (directory / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    if manifest.get('source') != 'IBKR_TWS_API_HISTORY':
        raise ValueError('native_gateway_capture_required')
    root = manifest.get('contract', {})
    if (root.get('symbol') != 'SPX' or root.get('security_type') != 'IND'
            or root.get('exchange') != 'CBOE' or root.get('currency') != 'USD'
            or type(root.get('contract_id')) is not int or root['contract_id'] <= 0):
        raise ValueError('native_spx_identity_required')
    entries = manifest.get('sessions', [])
    if not isinstance(entries, list) or not entries:
        raise ValueError('missing_session_inventory')
    days = [entry['date'] for entry in entries]
    # Validate dates before they may be used to construct file paths.
    if any(date.fromisoformat(day).isoformat() != day for day in days):
        raise ValueError('invalid_session_date')
    if days != sorted(set(days)):
        raise ValueError('session_dates_not_unique_and_ordered')
    if any(day >= EXCLUDED_FROM for day in days):
        raise ValueError('consumed_or_later_session_excluded')
    calendar = mcal.get_calendar('NYSE').schedule(start_date=days[0], end_date=days[-1])
    by_day = {str(day.date()): row for day, row in calendar.iterrows()}
    result, inventory = {}, []
    for entry in entries:
        day = entry['date']
        if day not in by_day:
            raise ValueError('non_trading_day')
        encoded = (directory / f'{day}.raw.json').read_bytes()
        if hashlib.sha256(encoded).hexdigest() != entry.get('raw_sha256'):
            raise ValueError('raw_hash_mismatch')
        raw = json.loads(encoded)
        if raw.get('contract') != root:
            raise ValueError('mixed_contracts')
        opened, closed = by_day[day].market_open, by_day[day].market_close
        expected = dict(endDateTime=request_end(closed), durationStr='1 D',
                        barSizeSetting='1 min', whatToShow='TRADES', useRTH=1,
                        formatDate=2, keepUpToDate=False)
        if raw.get('request') != expected:
            raise ValueError('unexpected_history_request')
        received = pd.Timestamp(raw['received_at'])
        if received.tz is None or received < closed:
            raise ValueError('session_not_complete_at_receipt')
        bounds = raw.get('provider_bounds')
        if not isinstance(bounds, dict) or not bounds.get('start') or not bounds.get('end'):
            raise ValueError('missing_provider_bounds')
        coverage = validate_session(raw['rows'], opened, closed)
        h = coverage.pop('history')
        inventory.append(dict(date=day, raw_sha256=entry['raw_sha256'], **coverage))
        frame = pd.DataFrame({k: h[k.lower()] for k in ('Open', 'High', 'Low', 'Close')},
                             index=pd.to_datetime(h['time'], utc=True))
        frame.attrs.update(symbol='SPX', security_type='IND')
        result[day] = frame
    if (manifest.get('data_complete') is not True or manifest.get('failure')
            or manifest.get('requested_sessions') != len(days)
            or any(not entry['complete'] for entry in inventory)):
        raise ValueError('incomplete_capture')
    return result, inventory, hashlib.sha256(manifest_bytes).hexdigest()


def chronological_days(days):
    days = sorted(days)
    if len(days) < 20:
        raise ValueError('need_at_least_20_independent_full_sessions')
    train_end, validation_size = int(len(days) * .6), int(len(days) * .2)
    result = dict(train=days[:train_end],
                  validation=days[train_end:train_end + validation_size],
                  holdout=days[train_end + validation_size:])
    if any(len(result[k]) < n for k, n in [('train', 12), ('validation', 4), ('holdout', 4)]):
        raise ValueError('insufficient_split_sizes')
    return result


def early_f1(metric):
    precision = metric.get('early_precision') or 0.
    recall = metric.get('early_event_recall') or 0.
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.


def select_training(models):
    # Candidate set, objective and tie-breakers were frozen before acquisition.
    return min(HYPOTHESES, key=lambda name: (
        -early_f1(models[name]['strict']['0']),
        models[name]['strict']['0']['false_alarms'], name))


def quality_gate(metric):
    lower = metric.get('precision_wilson_95')
    tests = dict(precision=(metric.get('precision') or 0) >= .5,
                 precision_wilson_lower=bool(lower and lower[0] >= .4),
                 early_recall=(metric.get('early_event_recall') or 0) >= .2,
                 median_lead=(metric.get('median_lead_minutes') or 0) >= 1,
                 false_alarms_per_session=metric.get('false_alarms_per_session') is not None
                 and metric['false_alarms_per_session'] <= 2)
    return dict(passed=all(tests.values()), checks=tests)


def evaluate_partition(dataset, days, models):
    config = ResearchConfig()
    bars = pd.concat([dataset[day] for day in days])
    bars.attrs.update(symbol='SPX', security_type='IND')
    f = features(bars)
    eligible = [i for i in range(len(bars) - config.horizon)
                if f.valid.iloc[i] and bars.index[i + config.horizon] - bars.index[i]
                == pd.Timedelta(minutes=config.horizon)]
    events = movement_events(bars, f, eligible, config)
    # Preserve the original label universe, then apply the existing conservative
    # wick-minute onset timestamp. No model's signals influence event creation.
    for event in events:
        i, side = event['anchor_index'], event['direction']
        threshold = bars.Close.iloc[i] + side * config.onset_fraction * event['target_points']
        future = bars.iloc[i + 1:event['target_index'] + 1]
        hits = np.flatnonzero((future.High >= threshold if side > 0 else future.Low <= threshold).to_numpy())
        event['onset_time'] = bars.index[i + 1 + int(hits[0])].isoformat()
    allowed, reports = set(eligible), {}
    for model in models:
        scheduled = signal_schedule(f, model)
        signals = [s for s in scheduled if s['index'] in allowed]
        report = dict(total_signals=len(scheduled), censored=len(scheduled) - len(signals),
                      strict={}, auxiliary={}, signal_matches={})
        for delay in (0, 1, 2):
            matched = [dict(s) for s in signals]
            report['strict'][str(delay)] = score_signals(
                events, matched, bars, eligible, 'rth', config,
                bootstrap=True, availability_delay_minutes=delay)
            report['auxiliary'][str(delay)] = preanchor_diagnostic(events, signals, bars, delay)
            report['signal_matches'][str(delay)] = matched
        reports[model] = report
    return dict(days=days, bars=len(bars), events=events, models=reports)


def reserve_holdout(days, manifest_sha256, registry):
    """Reserve session dates before computing outcomes, including failed attempts.

    Per-date exclusive creation prevents a recapture, new output name or an
    overlapping split from silently reusing the same held-out sessions.
    """
    registry = Path(registry) / PROTOCOL_COMMIT
    registry.mkdir(parents=True, exist_ok=True)
    for day in days:
        path = registry / f'{day}.json'
        reservation = dict(protocol_commit=PROTOCOL_COMMIT, session=day,
                           manifest_sha256=manifest_sha256,
                           reserved_at=datetime.now(timezone.utc).isoformat(),
                           status='CONSUMED_OR_RESERVED_DO_NOT_REUSE')
        try:
            with path.open('x', encoding='utf-8') as stream:
                json.dump(reservation, stream, indent=2)
                stream.write('\n')
        except FileExistsError:
            raise ValueError('holdout_session_already_reserved') from None


def study(dataset, inventory, manifest_sha256, before_holdout=None):
    splits = chronological_days(list(dataset))
    result = dict(protocol_commit=PROTOCOL_COMMIT, manifest_sha256=manifest_sha256,
                  mode='FROZEN_CHRONOLOGICAL_HISTORY_STUDY', inventory=inventory,
                  splits=splits, model_selected=None, holdout_opened=False,
                  readiness='NOT_READY', accepted=False, notifications_enabled=False,
                  orders_enabled=False, source='IBKR_TWS_API_HISTORY',
                  live_feed_verified=False,
                  limitations=['Historical OHLC cannot establish live arrival latency or option P&L.',
                               'Whole-session partitions prevent cross-boundary outcome overlap.',
                               'Wilson and session bootstrap intervals do not prove an edge.',
                               'Auxiliary pre-anchor results never decide acceptance.',
                               'Passing the study does not enable alerts or deploy a detector.'])
    result['train'] = evaluate_partition(dataset, splits['train'], MODELS)
    chosen = select_training(result['train']['models'])
    result['model_selected'] = chosen
    evaluated = (chosen, *BASELINES)
    result['validation'] = evaluate_partition(dataset, splits['validation'], evaluated)
    gate = quality_gate(result['validation']['models'][chosen]['strict']['0'])
    result['validation_gate'] = gate
    if not gate['passed']:
        result['reason'] = 'validation_failed_holdout_not_evaluated'
        return result
    if before_holdout is not None:
        try:
            before_holdout(splits['holdout'], result)
        except ValueError as exc:
            if str(exc) != 'holdout_session_already_reserved':
                raise
            result['reason'] = 'holdout_session_already_reserved'
            result['holdout_previously_reserved'] = True
            return result
    result['holdout_opened'] = True
    try:
        result['holdout'] = evaluate_partition(dataset, splits['holdout'], evaluated)
    except Exception as exc:
        # A failed calculation does not make a revealed holdout untouched again.
        result['reason'] = 'holdout_evaluation_failed_session_consumed'
        result['error_type'] = type(exc).__name__
        return result
    selected = result['holdout']['models'][chosen]['strict']['0']
    original = result['holdout']['models']['original_candidate']['strict']['0']
    result['holdout_gate'] = quality_gate(selected)
    result['holdout_improves_original_early_f1'] = early_f1(selected) > early_f1(original)
    result['accepted'] = (result['holdout_gate']['passed']
                          and result['holdout_improves_original_early_f1'])
    result['readiness'] = 'RESEARCH_GATES_PASSED' if result['accepted'] else 'NOT_READY'
    result['reason'] = 'research_only_requires_live_shadow_evidence' if result['accepted'] else 'holdout_failed'
    return result


def run_capture(capture, output, registry='.hunter-state/spx-holdout-locks'):
    output = Path(output)
    # Reserve the report path before any outcomes are computed. A crash leaves
    # an IN_PROGRESS record rather than a falsely untouched holdout.
    with output.open('x', encoding='utf-8') as stream:
        initial = dict(readiness='NOT_READY', reason='IN_PROGRESS',
                       accepted=False, holdout_opened=False)
        json.dump(initial, stream)
        stream.flush()

        def checkpoint(days, partial):
            reserve_holdout(days, partial['manifest_sha256'], registry)
            partial['holdout_opened'] = True
            partial['reason'] = 'HOLDOUT_RESERVED_EVALUATION_IN_PROGRESS'
            stream.seek(0)
            json.dump(partial, stream, indent=2, allow_nan=False)
            stream.truncate()
            stream.flush()

        try:
            dataset, inventory, digest = load_capture(capture)
            splits = chronological_days(list(dataset))
            if any((Path(registry) / PROTOCOL_COMMIT / f'{day}.json').exists()
                   for day in splits['train'] + splits['validation']):
                raise ValueError('previous_holdout_in_training_or_validation')
            result = study(dataset, inventory, digest, before_holdout=checkpoint)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result = dict(readiness='NOT_READY', accepted=False, holdout_opened=False,
                          protocol_commit=PROTOCOL_COMMIT,
                          reason=str(exc) if str(exc) in CAPTURE_FAILURES else 'capture_or_study_rejected',
                          error_type=type(exc).__name__, notifications_enabled=False, orders_enabled=False)
        stream.seek(0)
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.truncate()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--output', required=True, help='New result file; existing files are never replaced')
    parser.add_argument('--registry', default='.hunter-state/spx-holdout-locks',
                        help='Persistent holdout session reservations; keep across acquisitions')
    args = parser.parse_args()
    result = run_capture(args.capture, args.output, args.registry)
    print(json.dumps({k: result.get(k) for k in
                      ('readiness', 'reason', 'model_selected', 'holdout_opened')}))
    raise SystemExit(0 if result['accepted'] else 2)


if __name__ == '__main__':
    main()
