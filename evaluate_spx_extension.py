"""Fixed-rule limited SPX extension diagnostic. Never independent qualification."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_lead_v2 import MODELS as V2_MODELS, features, schedule
from research_spx_premove import MODELS as V1_MODELS, preanchor_diagnostic
from research_spx_premove import signal_schedule as v1_schedule

MODELS = (*V2_MODELS, *V1_MODELS)


def load_history(path):
    encoded = Path(path).read_bytes()
    payload = json.loads(encoded)
    root, h = payload['contract'], payload['history']
    if (root.get('symbol') != 'SPX' or root.get('country_code') != 'US'
            or root.get('exchange') != 'CBOE'
            or type(root.get('underlying_contract_id')) is not int or root['underlying_contract_id'] <= 0
            or not any(s.get('security_type') == 'IND' for s in root.get('sections', []))):
        raise ValueError('native_spx_required')
    if h.get('error'):
        raise ValueError('provider_history_error')
    keys = ('time', 'open', 'high', 'low', 'close')
    if any(not isinstance(h.get(k), list) for k in keys) or len({len(h[k]) for k in keys}) != 1 or not h['time']:
        raise ValueError('invalid_arrays')
    if any(pd.Timestamp(t).tz is None for t in h['time']):
        raise ValueError('aware_bar_time_required')
    received, chart_end = pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end'])
    if received.tz is None or chart_end.tz is None:
        raise ValueError('aware_completion_clock_required')
    index = pd.to_datetime(h['time'], utc=True)
    if not index.is_unique or not index.is_monotonic_increasing or not index.equals(index.floor('min')):
        raise ValueError('unordered_or_unaligned_bars')
    bars = pd.DataFrame({key: h[key.lower()] for key in ('Open', 'High', 'Low', 'Close')}, index=index)
    numbers = bars.to_numpy(dtype=float)
    if (not np.isfinite(numbers).all() or (numbers <= 0).any()
            or (bars.High < bars[['Open', 'Low', 'Close']].max(axis=1)).any()
            or (bars.Low > bars[['Open', 'Close']].min(axis=1)).any()):
        raise ValueError('invalid_ohlc')
    complete = bars.index + pd.Timedelta(minutes=1) <= min(received, chart_end)
    excluded = int((~complete).sum())
    bars = bars.loc[complete].copy()
    if bars.empty:
        raise ValueError('no_completed_bars')
    bars.attrs.update(symbol='SPX', security_type='IND')
    return bars, payload, hashlib.sha256(encoded).hexdigest(), excluded


def inventory(bars):
    labels = bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    calendar = mcal.get_calendar('NYSE').schedule(start_date=labels.min(), end_date=labels.max())
    days = {str(day.date()): row for day, row in calendar.iterrows()}
    rows = []
    for day, group in bars.groupby(labels, sort=True):
        if day not in days:
            raise ValueError('non_trading_day')
        session = days[day]
        expected = pd.date_range(session.market_open, session.market_close, freq='min', inclusive='left')
        outside = group.index.difference(expected)
        if len(outside):
            raise ValueError('outside_nyse_session')
        missing = expected.difference(group.index)
        rows.append(dict(date=day, bars=len(group), expected=len(expected),
                         complete=not len(missing), missing_minutes=[t.isoformat() for t in missing]))
    return rows


def evaluate_segment(day_bars, start, name):
    config = ResearchConfig()
    f = features(day_bars)
    eligible = [i for i in range(len(day_bars) - config.horizon)
                if day_bars.index[i] >= pd.Timestamp(start) and f.valid.iloc[i]
                and day_bars.index[i + config.horizon] - day_bars.index[i] == pd.Timedelta(minutes=config.horizon)]
    allowed = set(eligible)
    events = movement_events(day_bars, f, eligible, config)
    for event in events:
        i, side = event['anchor_index'], event['direction']
        threshold = day_bars.Close.iloc[i] + side * config.onset_fraction * event['target_points']
        future = day_bars.iloc[i + 1:event['target_index'] + 1]
        hits = np.flatnonzero((future.High >= threshold if side > 0 else future.Low <= threshold).to_numpy())
        event['onset_time'] = day_bars.index[i + 1 + int(hits[0])].isoformat()
    reports = {}
    for model in MODELS:
        # Run on the entire session first. Never reset cooldown at segment start.
        all_signals = schedule(f, model) if model in V2_MODELS else v1_schedule(f, model)
        segment_signals = [s for s in all_signals if day_bars.index[s['index']] >= pd.Timestamp(start)]
        signals = [s for s in segment_signals if s['index'] in allowed]
        report = dict(segment_candidates=len(segment_signals), censored=len(segment_signals) - len(signals),
                      strict={}, auxiliary={}, signal_matches={})
        for delay in (0, 1, 2):
            matched = [dict(s) for s in signals]
            report['strict'][str(delay)] = score_signals(events, matched, day_bars, eligible, 'rth', config,
                                                        bootstrap=False, availability_delay_minutes=delay)
            report['auxiliary'][str(delay)] = preanchor_diagnostic(events, signals, day_bars, delay)
            report['signal_matches'][str(delay)] = matched
        reports[model] = report
    return dict(name=name, start=pd.Timestamp(start).isoformat(),
                bars_in_segment=int((day_bars.index >= pd.Timestamp(start)).sum()),
                context_bars_before_segment=int((day_bars.index < pd.Timestamp(start)).sum()),
                events=events, models=reports, cooldown_carried_from_session_start=True)


def run(source, old_source, output, protocol_commit):
    bars, payload, digest, excluded = load_history(source)
    old, old_payload, old_digest, _ = load_history(old_source)
    if payload['contract']['underlying_contract_id'] != old_payload['contract']['underlying_contract_id']:
        raise ValueError('contract_changed')
    coverage = inventory(bars)
    if not all(any(row['date'] == day and row['complete'] for row in coverage)
               for day in ('2026-10-21', '2026-10-22')):
        raise ValueError('required_full_sessions_missing')
    overlap = old.index.intersection(bars.index)
    if len(overlap) != len(old):
        raise ValueError('old_overlap_not_fully_observed')
    changes = []
    for stamp in overlap:
        if not old.loc[stamp].equals(bars.loc[stamp]):
            changes.append(dict(time=stamp.isoformat(),
                                old=old.loc[stamp].to_dict(), new=bars.loc[stamp].to_dict()))
    labels = bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    oct21 = bars.loc[labels == '2026-10-21'].copy()
    oct22 = bars.loc[labels == '2026-10-22'].copy()
    oct21.attrs.update(symbol='SPX', security_type='IND')
    oct22.attrs.update(symbol='SPX', security_type='IND')
    segments = {
        'oct21_reverse_time_transfer': evaluate_segment(oct21, oct21.index[0], 'reverse_time_not_forward_validation'),
        'oct22_forward_tail_diagnostic': evaluate_segment(oct22, '2026-10-22T17:30:00Z', 'fixed_rule_forward_tail_only'),
    }
    result = dict(mode='LIMITED_EXTENSION_DIAGNOSTIC', protocol_commit=protocol_commit,
                  input_sha256=digest, old_input_sha256=old_digest, bars=len(bars),
                  excluded_partial_bars=excluded, coverage=coverage,
                  overlapping_completed_bars=len(overlap), overlap_revisions=changes,
                  segments=segments, readiness='NOT_READY', accepted=False, model_selected=None,
                  independent_quality_protocol_satisfied=False, holdout_opened=False,
                  notifications_enabled=False, orders_enabled=False, live_feed_verified=False,
                  limitations=['Only two full sessions and a partial third, not the frozen twenty-session study.',
                               'Oct21 predates development; it is reverse-time transfer, not forward validation.',
                               'Oct22 tail is a small historical segment with prior consumed context; not qualification.',
                               'All fixed models reported; no model selected, refitted or enabled.',
                               'Simulated delay is not measured latency; no option performance.'])
    with Path(output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--old-input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    result = run(args.input, args.old_input, args.output, args.protocol_commit)
    print('coverage', [(x['date'], x['bars'], x['complete']) for x in result['coverage']],
          'overlap_revisions', len(result['overlap_revisions']))
    for name, segment in result['segments'].items():
        print(name, 'events', len(segment['events']), 'bars', segment['bars_in_segment'])
        for model, report in segment['models'].items():
            m = report['strict']['0']
            print(model, {k: m[k] for k in ('signals', 'matched_events', 'early_matched_events', 'false_alarms', 'median_lead_minutes')})
