"""Fixed, no-orders comparison of real eligible plans; never imported by a reader."""
import argparse
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import es_signal_plan
from hunter_research import (DEFAULT_PARAMS, ResearchConfig, feature_frame,
    candidate_signal, chronological_splits, eligible_indices, movement_events,
    score_signals, validate_bars)
from hunter_runtime import HunterRuntime, futures_active
from strategy_rules import (PROXIMITY, MIN_RVOL, EXPIRY_MINUTES, COOLDOWN_MINUTES)


def rolling_features(bars):
    f = feature_frame(bars)
    f['level_high'] = f.range_high
    f['level_low'] = f.range_low
    f['near_high'] = (f.level_high-f.close)/f.atr
    f['near_low'] = (f.close-f.level_low)/f.atr
    return f


def baseline_candidate(f):
    side = candidate_signal(f, 'pre_level', {**DEFAULT_PARAMS, 'proximity': PROXIMITY, 'rvol': MIN_RVOL})
    if not side:
        return None
    return dict(direction=side, price=float(f['close']), atr=float(f['atr']),
                level=float(f['level_high'] if side > 0 else f['level_low']),
                invalidation=float(f['close']-side*f['atr']), rvol=float(f['rvol']))


def amd_candidate(f, row, tick=0.25):
    """Completed one-sided sweep/reclaim, no future swing pivot or invented POC."""
    if not f['valid'] or f['contraction'] > DEFAULT_PARAMS['contraction'] or f['rvol'] < MIN_RVOL:
        return None
    sweep_low = row.Low < f['range_low']
    sweep_high = row.High > f['range_high']
    if sweep_low == sweep_high:  # neither edge, or ambiguous two-sided sweep
        return None
    side = (1 if sweep_low and f['range_low'] < row.Close < f['range_high'] and row.Close > row.Open
            else -1 if sweep_high and f['range_low'] < row.Close < f['range_high'] and row.Close < row.Open else 0)
    if not side:
        return None
    return dict(direction=side, price=float(row.Close), atr=float(f['atr']),
                level=float(f['range_low'] if side > 0 else f['range_high']),
                invalidation=float(row.Low-tick if side > 0 else row.High+tick), rvol=float(f['rvol']))


class MemoryRuntime(HunterRuntime):
    def __init__(self, detector):
        self.detector = detector
        self.state = {'version': 1, 'symbols': {}, 'pending': [], 'notifications': {}}
        self.price_context_status = {}
        self.persistence_error = None

    def _record(self, entry):
        pass


def replay(bars, features):
    rows = [row for _, row in features.iterrows()]
    runtime = MemoryRuntime(lambda data, index: baseline_candidate(rows[index]))
    plans = {'current': [], 'amd': []}
    triggers = {'current': [], 'amd': []}
    rejected = {'current': [], 'amd': []}
    setups = []; waits = []; active = None; cooldown = None
    # Only the irrelevant annotation and repeated feature computation are skipped.
    # Actual lifecycle and complete_plan code still execute in this isolated process.
    with patch('price_action_context.observe', return_value={'status': 'replay_skipped'}), \
         patch.object(es_signal_plan, 'causal_features', side_effect=lambda data, index: rows[index].to_dict() if rows[index]['valid'] else None):
        for i, (start, row) in enumerate(bars.iterrows()):
            end = start+pd.Timedelta(minutes=1)
            now = end.to_pydatetime()
            valid = bool(rows[i]['valid']) and futures_active(now)
            if not valid:
                runtime._cancel('ES=F', now, {'last_completed_bar': end.isoformat()}, 'invalid_or_closed')
                if active:
                    active = None; cooldown = end+pd.Timedelta(minutes=COOLDOWN_MINUTES)
                continue
            previous = runtime.state['symbols'].get('ES=F', {}).get('active', {})
            started = previous.get('started_at')
            events = runtime._process_bar('ES=F', bars, i, now)
            for event in events:
                if event['state'] == 'SETUP':
                    setups.append(i)
                if event['state'] == 'TRIGGER':
                    waits.append((end-pd.Timestamp(started)).total_seconds()/60)
                    triggers['current'].append(i)
                    plan, reason = es_signal_plan.complete_plan(event, bars)
                    if plan:
                        plans['current'].append(dict(index=i, direction=1 if event['direction']=='UP' else -1,
                            bar_time=start.isoformat(), detected_at=end.isoformat()))
                    else:
                        rejected['current'].append(dict(index=i, reason=reason))
            if active:
                if active['direction']*(row.Close-active['invalidation']) <= 0 or end-active['started'] >= pd.Timedelta(minutes=EXPIRY_MINUTES):
                    active = None; cooldown = end+pd.Timedelta(minutes=COOLDOWN_MINUTES)
                continue
            if cooldown is not None and end < cooldown:
                continue
            candidate = amd_candidate(rows[i], row)
            if candidate:
                active = {**candidate, 'started': end}
                triggers['amd'].append(i)
                event = {**candidate, 'symbol': 'ES=F', 'state': 'TRIGGER',
                    'direction': 'UP' if candidate['direction']>0 else 'DOWN',
                    'bar_end': end.isoformat(), 'detected_at': end.isoformat(),
                    'reason': 'completed_amd_sweep_reclaim', 'event_id': 'amd-'+str(i)}
                plan, reason = es_signal_plan.complete_plan(event, bars)
                if plan:
                    plans['amd'].append(dict(index=i, direction=candidate['direction'],
                        bar_time=start.isoformat(), detected_at=end.isoformat()))
                else:
                    rejected['amd'].append(dict(index=i, reason=reason))
    return plans, dict(setups=setups, triggers=triggers, rejections=rejected,
                      current_setup_to_trigger_minutes=waits)


def f1(metrics):
    p, r = metrics['early_precision'] or 0, metrics['early_event_recall'] or 0
    return 2*p*r/(p+r) if p+r else 0.


def improvement_gate(old, new):
    return bool(old['sessions'] >= 5 and new['sessions'] >= 5 and
                old['signals'] >= 20 and new['signals'] >= 20 and
                f1(new) > f1(old) and new['precision'] >= old['precision'] and
                new['false_alarms_per_session'] <= old['false_alarms_per_session'] and
                old['median_lead_minutes'] is not None and new['median_lead_minutes'] is not None and
                new['median_lead_minutes'] >= old['median_lead_minutes'])


def compare(path, output):
    root = Path(__file__).resolve().parent
    raw = path.read_bytes()
    bars = validate_bars(pd.read_csv(path, index_col=0, parse_dates=True))
    features = rolling_features(bars)
    config = ResearchConfig()
    splits, inventory = chronological_splits(bars, 'rth', pd.Timestamp('2026-10-19T00:00Z'), config.horizon)
    print('Frozen protocol, features and partitions ready; replaying both models.', flush=True)
    plans, diagnostics = replay(bars, features)
    output.mkdir(parents=True, exist_ok=True)
    results = {}; gates = []
    for phase, indices in splits.items():
        eligible = eligible_indices(bars, features, indices, config)
        events = movement_events(bars, features, eligible, config)
        allowed, observable = set(indices), set(eligible)
        results[phase] = {}
        pd.DataFrame(events).to_csv(output/(phase+'_events.csv'), index=False)
        for delay in (0, 1):
            by_model = {}
            for model, signals in plans.items():
                selected = [dict(s, outcome_observable=s['index'] in observable) for s in signals if s['index'] in allowed]
                scored = [dict(s) for s in selected if s['outcome_observable']]
                metrics = score_signals(events, scored, bars, eligible, 'rth', config,
                                        bootstrap=True, availability_delay_minutes=delay)
                metrics.update(early_f1=f1(metrics), candidate_signals_total=len(selected),
                               censored_signals=len(selected)-len(scored))
                by_model[model] = metrics
                pd.DataFrame(selected).to_csv(output/f'{phase}_{model}_delay{delay}_signals.csv', index=False)
            results[phase][str(delay)] = by_model
            if phase in ('validation', 'test'):
                gates.append(improvement_gate(by_model['current'], by_model['amd']))
    diagnostics['counts'] = {model: {'triggers': len(diagnostics['triggers'][model]),
        'complete_plans': len(plans[model]), 'blocked': dict(Counter(r['reason'] for r in diagnostics['rejections'][model]))}
        for model in plans}
    waits = pd.Series(diagnostics['current_setup_to_trigger_minutes'], dtype=float)
    diagnostics['latency'] = {'minimum': float(waits.min()) if len(waits) else None,
        'median': float(waits.median()) if len(waits) else None,
        'p95': float(waits.quantile(.95)) if len(waits) else None}
    report = dict(created_at=datetime.now(timezone.utc).isoformat(), input_sha256=hashlib.sha256(raw).hexdigest(),
        rows=len(bars), first_bar=bars.index[0].isoformat(), last_bar=bars.index[-1].isoformat(),
        protocol_sha256=hashlib.sha256((root/'docs/AMD_COMPARISON_PROTOCOL.md').read_bytes()).hexdigest(),
        source='retained Yahoo ES continuous proxy; not native SPX/options or live-latency evidence',
        historical_test_previously_used=True, splits={phase: {'first': bars.index[min(ii)].isoformat(),
        'last': bars.index[max(ii)].isoformat()} for phase, ii in splits.items()},
        results=results, diagnostics=diagnostics, necessary_improvement_gate=all(gates),
        live_promotion=False, reason='No promotion without passed comparison AND genuinely unseen native validation.')
    (output/'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(json.dumps({'gate': all(gates), 'diagnostics': diagnostics['counts'],
                      'latency': diagnostics['latency'], 'output': str(output)}, indent=2), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('artifacts/issue16/data/es_1m.csv.gz'))
    parser.add_argument('--output', type=Path, default=Path('artifacts/amd_reclaim_comparison'))
    args = parser.parse_args()
    compare(args.input, args.output)
