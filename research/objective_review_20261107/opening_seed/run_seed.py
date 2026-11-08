"""Opening-seed variant of the wave detector versus the unchanged control.

Single change (see protocol.json): the ATR6 window at the open is seeded with
the last six 5m true ranges of the immediately preceding XNYS session. Offline
research only. No fitting, notifications, orders or option prices.
"""
import argparse
import gzip
import hashlib
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / 'wave_capture'))
import exchange_calendars as xc  # noqa: E402
from objective_review import Bar, NY, RIYADH, input_bytes, load_sessions  # noqa: E402
from run import (SPLIT, aggregate5, atr_before, coverage, detect, match_legs,  # noqa: E402
                 reference_legs, score, summarize, med)

CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2026-12-31')


def true_ranges(bars):
    """In-session true ranges; bar0 is high-low (no overnight gap)."""
    out = []
    for j, b in enumerate(bars):
        out.append(b.high-b.low if j == 0 else
                   max(b.high-b.low, abs(b.high-bars[j-1].close), abs(b.low-bars[j-1].close)))
    return out


def seeded_atr_before(bars, i, seed):
    """ATR of the six true ranges strictly before index i.

    seed: the last six true ranges of the preceding session, or None.
    For i>=6 this equals the control atr_before(bars, i).
    """
    if i >= 6:
        return atr_before(bars, i)
    if seed is None:
        return None
    if len(seed) != 6:
        raise ValueError('Seed must contain six prior true ranges')
    window = list(seed[i:]) + true_ranges(bars[:i])
    return sum(window)/6


def detect_seeded(bars, seed):
    """Identical state machine to wave_capture.detect except the ATR source."""
    side = 0
    low = high = None
    low_r = high_r = None
    last_emit = -100
    out = []
    for i, b in enumerate(bars):
        atr = seeded_atr_before(bars, i, seed)
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
            if i-last_emit >= 6:
                out.append({'index': i, 'decision': b.at+timedelta(minutes=5), 'side': side, 'r': r})
                last_emit = i
    return out


def previous_session(day):
    return str(CAL.previous_session(day).date())


def seeds_for(sessions5):
    """Map day -> seed (last six TRs of immediately preceding accepted session) or None."""
    by_day = {day: bars for day, bars in sessions5}
    seeds = {}
    for day, _ in sessions5:
        prior = by_day.get(previous_session(day))
        seeds[day] = true_ranges(prior)[-6:] if prior is not None and len(prior) >= 6 else None
    return seeds


def pre_onset(bars, signals, legs):
    """Descriptive: same-side signal within 15m (3 bars) BEFORE the leg start."""
    return sum(any(s['side'] == l['side'] and l['start']-3 <= s['index'] < l['start'] for s in signals)
               for l in legs)


def evaluate(sessions, seeds, variant):
    rows, legs_all, pre = [], [], {}
    for day, raw, step, closing, bars in sessions:
        signals = detect(bars) if variant == 'control' else detect_seeded(bars, seeds.get(day))
        legs = reference_legs(bars)
        pre[day] = pre_onset(bars, signals, legs)
        legs_all.extend(dict(r, day=day) for r in match_legs(bars, signals, legs))
        for signal in signals:
            for delay in (0, 15, 60):
                rows.append(dict(score(raw, step, closing, signal, signal['side'], delay),
                                 day=day, delay=delay, side=signal['side'], index=signal['index'],
                                 decision_Riyadh=signal['decision'].astimezone(RIYADH).isoformat()))
    return rows, legs_all, pre


def block_report(days, rows, legs, pre):
    day_set = set(days)
    sub = [r for r in rows if r['day'] in day_set]
    lg = [l for l in legs if l['day'] in day_set]
    signals = sum(r['delay'] == 0 for r in sub)
    cov = coverage(lg, signals)
    opening = [l for l in lg if l['start'] < 8]
    cov.update(unmatched_signals_per_session=round((signals-cov['matched_before75pct'])/len(days), 3),
               opening40m_legs=len(opening), opening40m_early=sum(l['early'] for l in opening),
               opening40m_matched=sum(l['matched'] for l in opening),
               legs_ended_before_index2=sum(l['end'] < 2 for l in lg),
               pre_onset_same_side_within15m=sum(pre[d] for d in days))
    return {'sessions': len(days), 'coverage': cov,
            'execution': {str(d): summarize([r for r in sub if r['delay'] == d]) for d in (0, 15, 60)}}


def as_sessions(loaded):
    return [(day, raw, step, closing, aggregate5(raw, step)) for day, raw, _, step, closing in loaded]


def forward_sessions(archive_path, after):
    """Complete regular sessions after `after` from the frozen-forward 5m archive."""
    a = json.loads(Path(archive_path).read_text())
    if a.get('chart_step') != 300:
        raise ValueError('Expected 5m archive')
    bars = {}
    for t, o, h, lo, c in zip(a['time'], a['open'], a['high'], a['low'], a['close']):
        at = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(NY)
        bars[at] = Bar(at, o, h, lo, c)
    out, excluded = [], []
    end = datetime.fromisoformat(a['chart_end'].replace('Z', '+00:00'))
    for ts in CAL.sessions_in_range('2026-10-21', end.date().isoformat()):
        day = str(ts.date())
        opening = CAL.session_open(day).to_pydatetime().astimezone(NY)
        closing = CAL.session_close(day).to_pydatetime().astimezone(NY)
        grid = [opening+timedelta(minutes=5*i) for i in range(int((closing-opening).total_seconds()//300))]
        if all(g in bars for g in grid):
            out.append((day, [bars[g] for g in grid], 5, closing, [bars[g] for g in grid]))
        else:
            excluded.append({'day': day, 'reason': 'incomplete_regular_grid_in_archive',
                             'present': sum(g in bars for g in grid), 'expected': len(grid)})
    meta = {k: a.get(k) for k in ('source', 'delayed', 'chart_start', 'chart_end', 'expires')}
    return out, excluded, meta


def consistency(main_sessions, fwd_sessions):
    """Compare overlapping 5m bars between the 116-session input and the forward archive."""
    m = {d: b for d, _, _, _, b in main_sessions}
    out = {}
    for day, _, _, _, bars in fwd_sessions:
        if day in m:
            pairs = list(zip(m[day], bars))
            if any(x.at != y.at for x, y in pairs) or len(m[day]) != len(bars):
                out[day] = {'aligned': False}
                continue
            diffs = [abs(x.close-y.close) for x, y in pairs]
            out[day] = {'aligned': True, 'bars': len(pairs), 'max_abs_close_diff': round(max(diffs), 4),
                        'bars_close_diff_gt_0p05': sum(d > .05 for d in diffs)}
    return out


def run(data, protocol, archive):
    loaded, excluded = load_sessions(data)
    sessions = as_sessions(loaded)
    seeds = seeds_for([(d, b) for d, _, _, _, b in sessions])
    days = [s[0] for s in sessions]
    groups = {'older': [d for d in days if d < SPLIT], 'recent': [d for d in days if d >= SPLIT], 'all': days}
    res = {v: evaluate(sessions, seeds, v) for v in ('control', 'seeded')}
    report = {v: {g: block_report(ds, *res[v]) for g, ds in groups.items()} for v in res}

    early = {v: {} for v in res}
    for v in res:
        for l in res[v][1]:
            early[v][l['day']] = early[v].get(l['day'], 0) + l['early']
    diffs = [early['seeded'].get(d, 0)-early['control'].get(d, 0) for d in days]
    rng = random.Random(801)
    boot = sorted(sum(rng.choices(diffs, k=len(diffs))) for _ in range(1000))
    paired = {'seeded_minus_control_early_matches': sum(diffs),
              'paired_session_bootstrap_95': [boot[24], boot[974]],
              'sessions_better': sum(x > 0 for x in diffs), 'sessions_worse': sum(x < 0 for x in diffs)}

    c, s = report['control'], report['seeded']
    checks = {}
    for g in ('older', 'recent'):
        checks[g] = {
            'early_improved': s[g]['coverage']['early_before25pct'] > c[g]['coverage']['early_before25pct'],
            'matched75_not_lower': s[g]['coverage']['matched_before75pct'] >= c[g]['coverage']['matched_before75pct'],
            'unmatched_per_session_increase_le_0p5':
                s[g]['coverage']['unmatched_signals_per_session'] - c[g]['coverage']['unmatched_signals_per_session'] <= .5}
    checks['bootstrap_lower_gt_0'] = paired['paired_session_bootstrap_95'][0] > 0
    passes = all(all(v.values()) for k, v in checks.items() if isinstance(v, dict)) and checks['bootstrap_lower_gt_0']

    fwd, fwd_excluded, meta = forward_sessions(archive, '2026-11-04')
    fwd_seeds = seeds_for([(d, b) for d, _, _, _, b in fwd])
    new_days = [d for d, *_ in fwd if d > max(days)]
    forward = {'source_meta': meta, 'classification': 'DELAYED_RESEARCH_ONLY (provider-declared delayed=900s; after-close replay, not a live receipt log)',
               'new_complete_sessions': new_days, 'excluded': fwd_excluded,
               'consistency_with_116_input_on_overlap': consistency(sessions, fwd)}
    if new_days:
        fr = {v: evaluate([x for x in fwd if x[0] in new_days], fwd_seeds, v) for v in ('control', 'seeded')}
        forward['report'] = {v: block_report(new_days, *fr[v]) for v in fr}
        forward['signals'] = {v: [r for r in fr[v][0] if r['delay'] == 0] for v in fr}
        forward['legs'] = {v: fr[v][1] for v in fr}
    forward['note'] = 'Descriptive only; too few sessions for any conclusion; never used for the decision.'

    return {'status': 'NOT_READY_RESEARCH_ONLY',
            'decision': 'QUALIFIES_FOR_UNUSED_PROSPECTIVE_SHADOW_ONLY' if passes else 'REJECT_CHANGE_KEEP_CONTROL',
            'input_sha256': hashlib.sha256(input_bytes(data)).hexdigest(),
            'protocol_sha256': hashlib.sha256(protocol.read_bytes()).hexdigest(),
            'excluded_sessions': excluded,
            'days_without_seed_fallback_to_control': [d for d in days if seeds[d] is None],
            'checks': checks, 'paired_early': paired, 'report': report, 'forward': forward,
            'legs': {v: res[v][1] for v in res},
            'signals': {v: [r for r in res[v][0] if r['delay'] == 0] for v in res}}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', type=Path, default=HERE.parent/'opening_validation_raw.json.gz')
    p.add_argument('--protocol', type=Path, default=HERE/'protocol.json')
    p.add_argument('--archive', type=Path, default=HERE.parents[1]/'frozen_forward_20261103/v2/checkpoints/20261106T203431709898Z/SPX_raw.json')
    p.add_argument('--out', type=Path, default=HERE/'results.json.gz')
    a = p.parse_args()
    result = run(a.data, a.protocol, a.archive)
    payload = (json.dumps(result, indent=2, allow_nan=False)+'\n').encode()
    a.out.write_bytes(gzip.compress(payload, mtime=0) if a.out.suffix == '.gz' else payload)
    print(json.dumps({k: v for k, v in result.items() if k not in ('legs', 'signals')}, indent=2,
                     default=str)[:200000])
