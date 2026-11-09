"""Offline SPX wave capture research. No model fitting or alerting."""
import argparse
import gzip
import hashlib
import json
import random
import statistics
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from objective_review import Bar, RIYADH, execute, input_bytes, load_sessions

SPLIT = '2026-09-14'


def aggregate5(raw, step):
    if step not in (1, 5):
        raise ValueError('Unsupported raw step')
    factor = 5 // step
    if len(raw) % factor:
        raise ValueError('Incomplete five-minute group')
    return [Bar(p[0].at, p[0].open, max(b.high for b in p), min(b.low for b in p), p[-1].close)
            for i in range(0, len(raw), factor) if (p := raw[i:i+factor])]


def atr_before(bars, i):
    if i < 6:
        return None
    values = []
    for j in range(i-6, i):
        b = bars[j]
        values.append(b.high-b.low if j == 0 else
                      max(b.high-b.low, abs(b.high-bars[j-1].close), abs(b.low-bars[j-1].close)))
    return sum(values)/6


def detect(bars):
    side = 0
    low = high = None
    low_r = high_r = None
    last_emit = -100
    out = []
    for i, b in enumerate(bars):
        atr = atr_before(bars, i)
        if atr is None:
            continue
        r = max(5.0, atr)
        if low is None:
            low = high = b.close
            low_r = high_r = r
            continue
        change = 0
        if side >= 0:
            if b.close > high:
                high, high_r = b.close, r
            if high-b.close >= high_r:
                change = -1
        if change == 0 and side <= 0:
            if b.close < low:
                low, low_r = b.close, r
            if b.close-low >= low_r:
                change = 1
        if change:
            side = change
            low = high = b.close
            low_r = high_r = r
            # Cooldown suppresses output, never postpones or rolls state back.
            if i-last_emit >= 6:
                out.append({'index': i, 'decision': b.at+timedelta(minutes=5),
                            'side': side, 'r': r})
                last_emit = i
    return out


def reference_legs(bars):
    """Offline hindsight segmentation; not available at the pivot time."""
    if not bars:
        return []
    pivot = extreme = 0
    low = high = 0
    direction = 0
    legs = []
    for i in range(1, len(bars)):
        price = bars[i].close
        if direction == 0:
            if price < bars[low].close:
                low = i
            if price > bars[high].close:
                high = i
            if price-bars[low].close >= 10:
                direction, pivot, extreme = 1, low, i
            elif bars[high].close-price >= 10:
                direction, pivot, extreme = -1, high, i
            continue
        if direction*(price-bars[extreme].close) > 0:
            extreme = i
        elif direction*(bars[extreme].close-price) >= 10:
            legs.append({'start': pivot, 'end': extreme, 'side': direction, 'terminal': False})
            pivot, extreme, direction = extreme, i, -direction
    if direction and extreme > pivot:
        legs.append({'start': pivot, 'end': extreme, 'side': direction, 'terminal': True})
    return [dict(leg, points=abs(bars[leg['end']].close-bars[leg['start']].close))
            for leg in legs if abs(bars[leg['end']].close-bars[leg['start']].close) >= 20]


def match_legs(bars, signals, legs):
    used = set()
    result = []
    for leg in legs:
        start, end = leg['start'], leg['end']
        row = dict(leg, start_Riyadh=(bars[start].at+timedelta(minutes=5)).astimezone(RIYADH).isoformat(),
                   end_Riyadh=(bars[end].at+timedelta(minutes=5)).astimezone(RIYADH).isoformat(),
                   matched=False, early=False)
        for n, signal in enumerate(signals):
            i = signal['index']
            if n in used or signal['side'] != leg['side'] or not start <= i < end:
                continue
            consumed = leg['side']*(bars[i].close-bars[start].close)
            fraction = consumed/leg['points']
            if not 0 <= fraction <= .75:
                continue
            used.add(n)
            row.update(matched=True, early=fraction <= .25, signal_index=i,
                       consumed_points=consumed, consumed_fraction=fraction,
                       lag_minutes=5*(i-start))
            break
        result.append(row)
    return result


def score(raw, step, closing, signal, side, delay):
    available = signal['decision']+timedelta(minutes=delay)
    next_bar = next((b for b in raw if b.at >= available), None)
    if next_bar is None:
        return {'status': 'NO_ENTRY_BEFORE_CLOSE'}
    event = dict(decision=signal['decision'], side=side, stop=next_bar.open-side*signal['r'])
    result = execute(raw, step, closing, event, delay, 30)
    if result['status'] == 'SCORED':
        end = next_bar.at+timedelta(minutes=30)
        window = [b for b in raw if next_bar.at <= b.at < end]
        # Diagnostic full-window excursions, including movement AFTER an earlier exit.
        result['window_mfe'] = max((b.high-next_bar.open if side == 1 else next_bar.open-b.low) for b in window)
        result['window_mae'] = max((next_bar.open-b.low if side == 1 else b.high-next_bar.open) for b in window)
        result['direction30_correct'] = side*(window[-1].close-next_bar.open) > 0
    return result


def med(values):
    return round(statistics.median(values), 3) if values else None


def summarize(rows):
    scored = [r for r in rows if r['status'] == 'SCORED']
    return {'events': len(rows), 'scored': len(scored), 'censored': len(rows)-len(scored),
            'positive_after_cost1': sum(r['gross_low'] > 1 for r in scored),
            'direction30_correct': sum(r['direction30_correct'] for r in scored),
            'ambiguous': sum(r['exit'] == 'ambiguous' for r in scored),
            'exit_counts': {key: sum(r['exit']==key for r in scored) for key in sorted({r['exit'] for r in scored})},
            'gross_lower_before_cost': round(sum(r['gross_low'] for r in scored),3),
            'net_lower': {str(c): round(sum(r['gross_low']-c for r in scored), 3) for c in (.5,1,2)},
            'net_upper_cost1': round(sum(r['gross_high']-1 for r in scored), 3),
            'median_full_window_mfe': med([r['window_mfe'] for r in scored]),
            'median_full_window_mae': med([r['window_mae'] for r in scored])}


def coverage(legs, signal_count):
    matched = [r for r in legs if r['matched']]
    return {'legs': len(legs), 'terminal_legs': sum(r['terminal'] for r in legs),
            'matched_before75pct': len(matched), 'missed': len(legs)-len(matched),
            'early_before25pct': sum(r['early'] for r in legs),
            'signals': signal_count,
            'signals_not_matched_to_reference': signal_count-len(matched),
            'unmatched_signals_per_session_note': 'Divide by group sessions; reference mismatch is not automatically a losing trade',
            'legs_ended_before_first_possible_signal': sum(r['end'] < 7 for r in legs),
            'median_lag_minutes_matched': med([r['lag_minutes'] for r in matched]),
            'median_consumed_points_matched': med([r['consumed_points'] for r in matched])}


def run(data, protocol):
    sessions, excluded = load_sessions(data)
    rows, all_legs, alternative = [], [], []
    for day, raw, _, step, closing in sessions:
        bars = aggregate5(raw, step)
        signals = detect(bars)
        all_legs.extend(dict(r, day=day) for r in match_legs(bars, signals, reference_legs(bars)))
        for signal in signals:
            for delay in (0,15,60):
                both = {side: score(raw, step, closing, signal, side, delay) for side in (1,-1)}
                record = {'day': day, 'delay': delay, 'side': signal['side'], 'r': signal['r'],
                          'decision_Riyadh': signal['decision'].astimezone(RIYADH).isoformat(),
                          'index': signal['index']}
                rows.append(dict(both[signal['side']], **record))
                alternative.append(dict(record, both=both))
    groups = {'older': [s[0] for s in sessions if s[0] < SPLIT],
              'recent': [s[0] for s in sessions if s[0] >= SPLIT], 'all': [s[0] for s in sessions]}
    report = {}
    for name, days in groups.items():
        day_set = set(days)
        subset = [r for r in rows if r['day'] in day_set]
        report[name] = {'sessions': len(days), 'coverage': coverage([r for r in all_legs if r['day'] in day_set], sum(r['delay']==0 for r in subset)),
                        'execution': {str(d): summarize([r for r in subset if r['delay']==d]) for d in (0,15,60)}}
        base = [r for r in alternative if r['day'] in day_set and r['delay']==0]
        report[name]['reversed_same_times'] = summarize([r['both'][-r['side']] for r in base])
        report[name]['always_up_same_times'] = summarize([r['both'][1] for r in base])
        buckets = defaultdict(list)
        for r in base:
            if r['both'][1]['status']=='SCORED' and r['both'][-1]['status']=='SCORED':
                buckets[r['day']].append(r)
        rng = random.Random(711)
        randomized = []
        day_means = {day: 0.0 for day in days}
        for _ in range(1000):
            total = 0.0
            for day in days:
                candidates = buckets[day]
                sides = [r['side'] for r in candidates]
                rng.shuffle(sides)
                value = sum(r['both'][side]['gross_low']-1 for r,side in zip(candidates,sides))
                total += value
                day_means[day] += value/1000
            randomized.append(total)
        actual = {day: sum(r['both'][r['side']]['gross_low']-1 for r in buckets[day]) for day in days}
        differences = [actual[day]-day_means[day] for day in days]
        rng = random.Random(712)
        boot = sorted(sum(rng.choices(differences,k=len(days))) for _ in range(1000))
        report[name]['randomized_same_times_cost1'] = {
            'replicates': 1000, 'mean_net': round(statistics.mean(randomized),3),
            'candidate_minus_mean_random': round(sum(differences),3),
            'paired_session_bootstrap_95': [round(boot[24],3),round(boot[974],3)]}
    missed_cases = []
    for leg in sorted((l for l in all_legs if not l['matched']),key=lambda l:-l['points']):
        candidates = [r for r in rows if r['day']==leg['day'] and r['delay']==0
                      and leg['start'] <= r['index'] < leg['end']]
        same_side = [r for r in candidates if r['side']==leg['side']]
        reason = ('ENDED_BEFORE_FIRST_POSSIBLE_SIGNAL' if leg['end'] < 7 else
                  'SAME_SIDE_SIGNAL_TOO_LATE_IN_REFERENCE_LEG' if same_side else
                  'OPPOSITE_SIDE_SIGNALS_ONLY' if candidates else 'NO_EMITTED_SIGNAL_DURING_LEG')
        missed_cases.append(dict(leg, reason=reason,
                                observed_signal_times=[r['decision_Riyadh'] for r in candidates]))
    passes = all(report[g]['execution']['0']['net_lower']['1']>0 for g in ('older','recent'))
    passes &= report['all']['randomized_same_times_cost1']['paired_session_bootstrap_95'][0]>0
    return {'status': 'NOT_READY_RESEARCH_ONLY', 'decision': 'UNUSED_PROSPECTIVE_TEST_ONLY' if passes else 'SUSPEND_PARAMETERIZATION',
            'input_sha256': hashlib.sha256(input_bytes(data)).hexdigest(),
            'protocol_sha256': hashlib.sha256(protocol.read_bytes()).hexdigest(),
            'excluded_sessions': excluded, 'report': report, 'signals': rows, 'reference_legs': all_legs,
            'missed_casebook': missed_cases}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=Path('opening_validation_raw.json.gz'))
    p.add_argument('--protocol', type=Path, default=Path('wave_capture/protocol.json'))
    p.add_argument('--out', type=Path, default=Path('wave_capture/results.json.gz'))
    args = p.parse_args()
    result = run(args.data,args.protocol)
    payload = (json.dumps(result,indent=2,allow_nan=False)+'\n').encode()
    args.out.write_bytes(gzip.compress(payload,mtime=0) if args.out.suffix=='.gz' else payload)
    print(json.dumps({k:v for k,v in result.items() if k not in ('signals','reference_legs','missed_casebook')},indent=2))
