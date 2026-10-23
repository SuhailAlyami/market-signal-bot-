"""Paired native30s midpoint/minute-close timing experiment; development only."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from evaluate_spx_extension import load_history
from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_lead_v2 import features, directions as lead_directions
from research_spx_premove import directions as v1_directions

MODELS = ('pullback_release', 'compression_0.35', 'prelevel_pressure')


def load_halves(path):
    encoded = Path(path).read_bytes()
    payload = json.loads(encoded)
    root, h = payload['contract'], payload['history']
    if (root.get('symbol') != 'SPX' or root.get('country_code') != 'US'
            or root.get('exchange') != 'CBOE'
            or not any(s.get('security_type') == 'IND' for s in root.get('sections', []))
            or type(root.get('underlying_contract_id')) is not int or root['underlying_contract_id'] <= 0):
        raise ValueError('native_spx_required')
    keys = ('time', 'open', 'high', 'low', 'close')
    if (h.get('error') or h.get('chart_step') != 30
            or any(not isinstance(h.get(k), list) for k in keys)
            or len({len(h[k]) for k in keys}) != 1 or not h['time']):
        raise ValueError('native_half_arrays_required')
    if any(pd.Timestamp(t).tz is None for t in h['time']):
        raise ValueError('aware_native_time_required')
    received, end = pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end'])
    if received.tz is None or end.tz is None:
        raise ValueError('aware_completion_clock_required')
    index = pd.to_datetime(h['time'], utc=True)
    if not index.is_unique or not index.is_monotonic_increasing or not index.equals(index.floor('30s')):
        raise ValueError('native_half_clock_invalid')
    bars = pd.DataFrame({k: h[k.lower()] for k in ('Open', 'High', 'Low', 'Close')}, index=index)
    values = bars.to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (values <= 0).any()
            or (bars.High < bars[['Open', 'Low', 'Close']].max(axis=1)).any()
            or (bars.Low > bars[['Open', 'Close']].min(axis=1)).any()):
        raise ValueError('invalid_native_ohlc')
    complete = bars.index + pd.Timedelta(seconds=30) <= min(received, end)
    return bars.loc[complete].copy(), payload, hashlib.sha256(encoded).hexdigest(), int((~complete).sum())


def minute_pairs(halves):
    groups = halves.groupby(halves.index.floor('min'))
    if any(len(g) != 2 or not g.index[0].second == 0 or not g.index[1].second == 30
           for _, g in groups):
        raise ValueError('missing_native_half_no_fill')
    out = groups.agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'})
    out.attrs.update(symbol='SPX', security_type='IND')
    return out


def midpoint_features(minutes, halves):
    """Current first half + known previous completed minutes only."""
    if minutes.index.tz_convert('America/New_York').normalize().nunique() != 1:
        raise ValueError('one_session_required')
    base = features(minutes)
    first = halves.reindex(minutes.index)
    mid = base.copy()
    mid['valid'] = base.valid.shift(1, fill_value=False)
    mid['close'] = first.Close
    mid['body'] = first.Close - first.Open
    mid['position'] = (first.Close-first.Low)/(first.High-first.Low).replace(0, np.nan)
    mid['move3'] = first.Close-minutes.Close.shift(3)
    mid['move15'] = first.Close-minutes.Close.shift(15)
    mid['ema5'] = (2/6)*first.Close+(1-2/6)*base.ema5.shift(1)
    mid['ema15'] = (2/16)*first.Close+(1-2/16)*base.ema15.shift(1)
    # base ATR/compression/levels exclude current minute. Full current close,
    # high/low or full-current EMA must not enter the midpoint decision.
    mid['slope5'] = (-2*minutes.Close.shift(4)-minutes.Close.shift(3)
                     +minutes.Close.shift(1)+2*first.Close)/10
    return base, mid


def candidate_directions(f, model):
    return lead_directions(f, model) if model == 'prelevel_pressure' else v1_directions(f, model)


def signals(f, model, clock, halves):
    delta = pd.Timedelta(seconds=30 if clock == 'midpoint' else 60)
    offset = pd.Timedelta(seconds=0 if clock == 'midpoint' else 30)
    result, until = [], None
    for timestamp, side in candidate_directions(f, model).items():
        decision = timestamp + delta
        if side and (until is None or decision >= until):
            native_index = halves.index.get_loc(timestamp + offset)
            result.append(dict(index=int(native_index), direction=int(side),
                               detected_at=decision.isoformat()))
            until = decision + pd.Timedelta(minutes=10)
    return result


def compare(minutes, halves):
    base, mid = midpoint_features(minutes, halves)
    floor = halves.index.floor('min')
    prior_valid = pd.Series(base.valid.shift(1, fill_value=False).reindex(floor).to_numpy(), index=halves.index)
    atr = pd.DataFrame({'atr': base.atr.reindex(floor).to_numpy()}, index=halves.index)
    config = ResearchConfig(horizon=20, cooldown=20)
    eligible = [i for i in range(len(halves)-20) if prior_valid.iloc[i]
                and atr.atr.iloc[i] > 0 and halves.index[i+20]-halves.index[i] == pd.Timedelta(minutes=10)]
    events = movement_events(halves, atr, eligible, config)
    for event in events:
        i, side = event['anchor_index'], event['direction']
        target = halves.Close.iloc[i]+side*config.onset_fraction*event['target_points']
        future = halves.iloc[i+1:event['target_index']+1]
        hit = np.flatnonzero((future.High >= target if side > 0 else future.Low <= target).to_numpy())[0]
        event['onset_time'] = halves.index[i+1+int(hit)].isoformat()
        event['anchor_known_at'] = (halves.index[i]+pd.Timedelta(seconds=30)).isoformat()
        event['target_time'] = (halves.index[event['target_index']]+pd.Timedelta(seconds=30)).isoformat()
    allowed, reports = set(eligible), {}
    for model in MODELS:
        reports[model] = {}
        for clock, f in [('midpoint', mid), ('minute_close', base)]:
            scheduled = signals(f, model, clock, halves)
            chosen = [s for s in scheduled if s['index'] in allowed]
            report = dict(candidates=len(scheduled), censored=len(scheduled)-len(chosen),
                          metrics={}, signal_matches={})
            for seconds in (0, 30, 60, 120):
                matched = [dict(s) for s in chosen]
                report['metrics'][str(seconds)] = score_signals(
                    events, matched, halves, eligible, 'rth', config,
                    bootstrap=False, availability_delay_minutes=seconds/60)
                report['signal_matches'][str(seconds)] = matched
            reports[model][clock] = report
    return dict(events=events, models=reports, eligible_half_anchors=len(eligible))


def run(source, minute_source, output, protocol_commit):
    native, root, digest, excluded = load_halves(source)
    calendar = mcal.get_calendar('NYSE').schedule(start_date='2026-10-22', end_date='2026-10-22').iloc[0]
    expected = pd.date_range(calendar.market_open, calendar.market_close, freq='30s', inclusive='left')
    day = native.loc[native.index.tz_convert('America/New_York').strftime('%Y-%m-%d') == '2026-10-22']
    if not day.index.equals(expected):
        raise ValueError('full_native_session_required')
    minutes = minute_pairs(day)
    prior, prior_root, prior_digest, _ = load_history(minute_source)
    if root['contract']['underlying_contract_id'] != prior_root['contract']['underlying_contract_id']:
        raise ValueError('contract_changed')
    if not minutes.index.isin(prior.index).all() or not minutes.equals(prior.loc[minutes.index]):
        raise ValueError('native_pair_differs_from_minute_capture')
    result = compare(minutes, day)
    result.update(mode='NATIVE_HALFMINUTE_PAIRED_DEVELOPMENT', protocol_commit=protocol_commit,
                  input_sha256=digest, minute_input_sha256=prior_digest,
                  acquired_native_bars=len(native), session_native_bars=len(day),
                  aggregated_minutes=len(minutes), exact_minute_crosscheck=True,
                  excluded_partial_native_bars=excluded,
                  readiness='NOT_READY', accepted=False, model_selected=None,
                  independent_validation=False, notifications_enabled=False, orders_enabled=False,
                  limitations=['Consumed Oct22 minute path with newly acquired historical intraminute detail.',
                               'New native-half event universe differs from frozen minute acceptance.',
                               'Compare clocks only on this common event universe; no old-count comparison.',
                               'Prior context/cooldown remain causal; no current second half in midpoint features.',
                               'Delivery delay is simulated, not measured; no live-feed, options or profit claim.'])
    with Path(output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input', required=True)
    p.add_argument('--minute-input', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--protocol-commit', required=True)
    args = p.parse_args()
    result = run(args.input, args.minute_input, args.output, args.protocol_commit)
    print('native events', len(result['events']), 'crosscheck', result['exact_minute_crosscheck'])
    for model, clocks in result['models'].items():
        for clock, row in clocks.items():
            m = row['metrics']['0']
            print(model, clock, {k: m[k] for k in ('signals', 'matched_events', 'early_matched_events', 'false_alarms', 'median_lead_minutes')},
                  'early by delay', [row['metrics'][str(d)]['early_matched_events'] for d in (0,30,60,120)])
