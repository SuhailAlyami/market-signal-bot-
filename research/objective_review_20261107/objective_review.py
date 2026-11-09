"""Declared SPX research screen. No fitting, notifications or trading."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
RIYADH = ZoneInfo('Asia/Riyadh')
COSTS = (0.5, 1.0, 2.0)
LATENCIES = (0, 15, 60)
SPLIT = '2026-09-14'


@dataclass(frozen=True)
class Bar:
    at: datetime
    open: float
    high: float
    low: float
    close: float


def input_bytes(path):
    data = path.read_bytes()
    return gzip.decompress(data) if path.suffix == ".gz" else data


def load_sessions(path):
    calendar = xc.get_calendar('XNYS', start='2026-01-01', end='2026-12-31')
    sessions, excluded, seen = [], [], set()
    for item in json.loads(input_bytes(path)):
        day, step = item['day'], item['step']
        if day in seen:
            raise ValueError('Duplicate session ' + day)
        seen.add(day)
        if step not in (1, 5) or not calendar.is_session(day):
            excluded.append({'day': day, 'reason': 'unsupported_step_or_not_session'})
            continue
        opening = calendar.session_open(day).to_pydatetime().astimezone(NY)
        closing = calendar.session_close(day).to_pydatetime().astimezone(NY)
        raw = []
        for row in csv.DictReader(io.StringIO(item['csv'])):
            at = datetime.fromisoformat(day + 'T' + row['time']).replace(tzinfo=NY)
            values = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
            if not all(math.isfinite(v) and v > 0 for v in values):
                raise ValueError('Invalid price ' + day)
            bar = Bar(at, *values)
            if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
                raise ValueError('Invalid OHLC ' + day)
            if opening <= at < closing:
                raw.append(bar)
        expected = [opening + timedelta(minutes=i) for i in range(0, int((closing-opening).total_seconds()/60), step)]
        if [bar.at for bar in raw] != expected:
            excluded.append({'day': day, 'reason': 'incomplete_or_unordered_regular_grid'})
            continue
        factor = 15 // step
        bars = []
        for i in range(0, len(raw), factor):
            part = raw[i:i+factor]
            bars.append(Bar(part[0].at, part[0].open, max(b.high for b in part),
                            min(b.low for b in part), part[-1].close))
        sessions.append((day, raw, bars, step, closing))
    return sorted(sessions), excluded


def first_event(bars, method):
    low = min(b.low for b in bars[:2])
    high = max(b.high for b in bars[:2])
    for i in range(2, len(bars)):
        bar, prior = bars[i], bars[i-1]
        if method == 'reclaim_30m':
            up = prior.close < low and bar.low < low and low < bar.close < high
            down = prior.close > high and bar.high > high and low < bar.close < high
            if up or down:
                side = 1 if up else -1
                stop = bar.low - .5 if up else bar.high + .5
                return {'decision': bar.at + timedelta(minutes=15), 'side': side, 'stop': stop}
        else:
            if bar.close > high or bar.close < low:
                side = 1 if bar.close > high else -1
                return {'decision': bar.at + timedelta(minutes=15), 'side': side,
                        'stop': low - .5 if side == 1 else high + .5}
    return None


def execute(raw, step, closing, event, delay, horizon):
    available = event['decision'] + timedelta(minutes=delay)
    found = [i for i, b in enumerate(raw) if b.at >= available]
    if not found:
        return {'status': 'NO_ENTRY_BEFORE_CLOSE'}
    index = found[0]
    entry_bar = raw[index]
    end = entry_bar.at + timedelta(minutes=horizon)
    if end > closing:
        return {'status': 'INSUFFICIENT_SAME_SESSION_HORIZON'}
    side, stop, entry = event['side'], event['stop'], entry_bar.open
    risk = side * (entry - stop)
    if risk <= 0:
        return {'status': 'ENTRY_BEYOND_STOP'}
    result = {'status': 'SCORED', 'side': side, 'entry': entry, 'stop': stop,
              'risk': risk, 'entry_Riyadh': entry_bar.at.astimezone(RIYADH).isoformat()}
    window = [b for b in raw[index:] if b.at < end]
    assert len(window) == horizon // step
    result['gross_low'] = result['gross_high'] = side * (window[-1].close - entry)
    result['exit'] = 'time'
    for bar in window:
        opening = side * (bar.open - entry)
        favorable = bar.high - entry if side == 1 else entry - bar.low
        adverse = entry - bar.low if side == 1 else bar.high - entry
        if opening <= -risk:
            result.update(gross_low=opening, gross_high=opening, exit='stop_gap')
            break
        if opening >= 2 * risk:
            result.update(gross_low=2*risk, gross_high=2*risk, exit='target_gap_capped')
            break
        if adverse >= risk:
            ambiguous = favorable >= 2*risk
            result.update(gross_low=-risk, gross_high=2*risk if ambiguous else -risk,
                          exit='ambiguous' if ambiguous else 'stop')
            break
        if favorable >= 2*risk:
            result.update(gross_low=2*risk, gross_high=2*risk, exit='target')
            break
    return result


def summary(trades, days):
    scored = [t for t in trades if t['status'] == 'SCORED']
    points = [t['gross_low'] - 1 for t in scored]
    daily = {day: 0.0 for day in days}
    for t in scored:
        daily[t['day']] += t['gross_low'] - 1
    cumulative = peak = drawdown = 0.0
    for day in sorted(daily):
        cumulative += daily[day]
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak-cumulative)
    rng = random.Random(711)
    values = list(daily.values())
    samples = sorted(sum(rng.choices(values, k=len(values))) for _ in range(1000))
    return {'events': len(trades), 'scored': len(scored),
            'excluded': len(trades)-len(scored), 'positive_at_1_point': sum(p > 0 for p in points),
            'ambiguous': sum(t['exit'] == 'ambiguous' for t in scored),
            'net_lower': {str(c): round(sum(t['gross_low']-c for t in scored), 2) for c in COSTS},
            'net_upper': {str(c): round(sum(t['gross_high']-c for t in scored), 2) for c in COSTS},
            'without_largest_winner_at_1': round(sum(points)-max([0.0]+points), 2),
            'max_drawdown_points_at_1': round(drawdown, 2),
            'session_bootstrap_total_95_at_1': [round(samples[24], 2), round(samples[974], 2)]}


def run(data, protocol):
    sessions, excluded = load_sessions(data)
    groups = {'older': [s for s in sessions if s[0] < SPLIT],
              'recent': [s for s in sessions if s[0] >= SPLIT], 'all': sessions}
    rows, comparisons = [], {}
    for method, horizon in [('reclaim_30m', 30), ('breakout_90m', 90)]:
        for day, raw, bars, step, closing in sessions:
            event = first_event(bars, method)
            if event is None:
                continue
            for delay in LATENCIES:
                result = execute(raw, step, closing, event, delay, horizon)
                rows.append(dict(result, day=day, method=method, delay=delay,
                                 decision_Riyadh=event['decision'].astimezone(RIYADH).isoformat()))
        comparisons[method] = {}
        for delay in LATENCIES:
            comparisons[method][str(delay)] = {
                name: summary([r for r in rows if r['method']==method and r['delay']==delay
                               and r['day'] in {s[0] for s in group}], [s[0] for s in group])
                for name, group in groups.items()}
        zero = comparisons[method]['0']
        comparisons[method]['decision'] = ('SUSPEND_PARAMETERIZATION' if any(
            zero[group]['net_lower']['1.0'] <= 0 for group in ('older', 'recent'))
            else 'REQUIRES_UNUSED_PROSPECTIVE_TEST')
    daily = []
    for day, raw, bars, step, closing in sessions:
        side = (bars[1].close > bars[0].open) - (bars[1].close < bars[0].open)
        move = bars[-1].close - bars[1].close
        daily.append({'day': day, 'side': side, 'remaining_points': move,
                      'flat_prediction': side == 0, 'flat_outcome': move == 0,
                      'correct': side*move > 0, 'always_up_correct': move > 0})
    return {'status': 'EXPLORATORY_RESEARCH_ONLY_NOT_READY',
            'input_sha256': hashlib.sha256(input_bytes(data)).hexdigest(),
            'protocol_sha256': hashlib.sha256(protocol.read_bytes()).hexdigest(),
            'complete_sessions': len(sessions), 'excluded_sessions': excluded,
            'comparisons': comparisons,
            'daily_direction': {name: {'n': len(group),
                'flat_predictions': sum(r['flat_prediction'] for r in daily if r['day'] in {s[0] for s in group}),
                'flat_outcomes': sum(r['flat_outcome'] for r in daily if r['day'] in {s[0] for s in group}),
                'correct': sum(r['correct'] for r in daily if r['day'] in {s[0] for s in group}),
                'always_up_correct': sum(r['always_up_correct'] for r in daily if r['day'] in {s[0] for s in group})}
                for name, group in groups.items()},
            'trades': rows, 'daily_forecasts': daily}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=Path('objective_protocol.json'))
    parser.add_argument('--out', type=Path, default=Path('objective_results.json'))
    args = parser.parse_args()
    result = run(args.data, args.protocol)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps({k: v for k, v in result.items() if k not in ('trades', 'daily_forecasts')}, indent=2))
