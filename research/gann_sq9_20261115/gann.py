"""Square-of-Nine level test on SPX 5m bars (protocol.json). Research only; nothing is fitted."""
import hashlib
import json
import math
import random
import statistics as st
import sys
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent/'objective_review_20261107'
sys.path.insert(0, str(ROOT))
from objective_review import Bar, load_sessions  # noqa: E402
import exchange_calendars as xc  # noqa: E402

CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2026-12-31')
SPLIT = '2026-09-14'
KS = (-3, -2, -1, 1, 2, 3)
COSTS = (0.5, 1.0, 2.0)


def to5(raw, step):
    f = 5//step
    return [Bar(p[0].at, p[0].open, max(b.high for b in p), min(b.low for b in p), p[-1].close)
            for i in range(0, len(raw), f) if (p := raw[i:i+f])]


def setups(bar, levels, step):
    """Return candidate setups on a closed bar: (dist, level_index, kind, side)."""
    out = []
    for k, L in levels:
        o, h, lo, c = bar.open, bar.high, bar.low, bar.close
        if o < L and c >= L+0.25*step:
            out.append((abs(c-L), k, 'break', 1, L))
        elif o > L and c <= L-0.25*step:
            out.append((abs(c-L), k, 'break', -1, L))
        elif L > o and h >= L and c < L:
            out.append((abs(c-L), k, 'reject', -1, L))
        elif L < o and lo <= L and c > L:
            out.append((abs(c-L), k, 'reject', 1, L))
    out.sort(key=lambda x: (x[0], 0 if x[2] == 'break' else 1))
    return out


def exit_trade(bars, j0, side, stop, target):
    """Walk bars from j0 (entry bar). Worst case stop first; stop gap at open; target capped."""
    for j in range(j0, len(bars)):
        b = bars[j]
        if side == 1:
            if b.open <= stop and j > j0:
                return b.open, j, 'stop_gap'
            if b.low <= stop:
                return stop, j, 'stop'
            if b.high >= target:
                return target, j, 'target'
        else:
            if b.open >= stop and j > j0:
                return b.open, j, 'stop_gap'
            if b.high >= stop:
                return stop, j, 'stop'
            if b.low <= target:
                return target, j, 'target'
    return bars[-1].close, len(bars)-1, 'session_close'


def simulate_day(bars, closing, base, step):
    levels = [(k, base+k*step) for k in KS]
    used, trades, i = set(), [], 0
    last_entry_start = closing-timedelta(minutes=15)
    while i < len(bars)-1:
        cands = [c for c in setups(bars[i], levels, step) if (c[1], c[2], c[3]) not in used]
        nxt = bars[i+1]
        if cands and nxt.at < last_entry_start:
            _, k, kind, side, L = cands[0]
            used.add((k, kind, side))
            stop, target, entry = L-side*0.25*step, L+side*step, nxt.open
            if side*(entry-stop) > 0 and side*(target-entry) > 0:
                px, j, why = exit_trade(bars, i+1, side, stop, target)
                trades.append({'entry_at': nxt.at.isoformat(), 'side': side, 'kind': kind, 'k': k, 'entry': entry,
                               'exit': px, 'exit_reason': why, 'gross': side*(px-entry)})
                i = j  # flat after the exit bar's close; that bar may itself signal
                continue
        i += 1
    return trades


def sessions_with_base():
    loaded, _ = load_sessions(ROOT/'opening_validation_raw.json.gz')
    by = {d: (d, raw, step, closing) for d, raw, _, step, closing in loaded}
    out = []
    for d in sorted(by):
        if d >= '2026-11-05':
            continue
        prev = str(CAL.previous_session(d).date())
        if prev not in by:
            continue
        pb = to5(by[prev][1], by[prev][2])
        out.append({'day': d, 'bars': to5(by[d][1], by[d][2]), 'closing': by[d][3], 'base': pb[-1].close,
                    'prev_range': max(b.high for b in pb)-min(b.low for b in pb)})
    return out


def metrics(trades, cost=1.0):
    net = [t['gross']-cost for t in trades]
    cum, peak, mdd = 0.0, 0.0, 0.0
    for v in net:
        cum += v; peak = max(peak, cum); mdd = max(mdd, peak-cum)
    return {'trades': len(trades), 'net': round(sum(net), 2), 'expectancy': round(st.mean(net), 3) if net else None,
            'max_drawdown': round(mdd, 2), 'win_rate': round(sum(v > 0 for v in net)/len(net), 3) if net else None}


def boot_ci(trades_by_day, days, cost=1.0, seed=1502, draws=2000):
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = rng.choices(days, k=len(days))
        n = [t['gross']-cost for d in pick for t in trades_by_day.get(d, [])]
        if n:
            vals.append(sum(n)/len(n))
    vals.sort()
    return [round(vals[int(.025*len(vals))], 3), round(vals[int(.975*len(vals))-1], 3)]


def run():
    S = sessions_with_base()
    blocks = {'development': [s for s in S if s['day'] < SPLIT], 'test': [s for s in S if s['day'] >= SPLIT]}
    out = {'protocol_sha256': hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
           'sessions': {k: [len(v), v[0]['day'], v[-1]['day']] for k, v in blocks.items()}}
    for name, ss in blocks.items():
        g = {s['day']: simulate_day(s['bars'], s['closing'], s['base'], math.sqrt(s['base'])/2) for s in ss}
        v = {s['day']: simulate_day(s['bars'], s['closing'], s['base'], 0.5*s['prev_range']) for s in ss}
        allg = [t for s in ss for t in g[s['day']]]
        allv = [t for s in ss for t in v[s['day']]]
        days = [s['day'] for s in ss]
        res = {'gann': {str(c): metrics(allg, c) for c in COSTS}, 'gann_ci95_expectancy_cost1': boot_ci(g, days),
               'gann_exit_reasons': {r: sum(t['exit_reason'] == r for t in allg) for r in ('target', 'stop', 'stop_gap', 'session_close')},
               'gann_by_kind_cost1': {k: metrics([t for t in allg if t['kind'] == k]) for k in ('reject', 'break')},
               'median_step_points': round(st.median(math.sqrt(s['base'])/2 for s in ss), 2),
               'median_vol_step_points': round(st.median(0.5*s['prev_range'] for s in ss), 2),
               'control_vol': {str(c): metrics(allv, c) for c in COSTS}, 'no_signal_net': 0}
        rng = random.Random(1501)
        anc = []
        for _ in range(200):
            tr = []
            for s in ss:
                step = math.sqrt(s['base'])/2
                tr += simulate_day(s['bars'], s['closing'], s['base']+rng.uniform(-.5, .5)*step, step)
            anc.append(metrics(tr)['net'])
        anc.sort()
        res['control_anchor_net_cost1'] = {'median': anc[100], 'p5': anc[10], 'p95': anc[190], 'gann_rank_pct': round(sum(a < res['gann']['1.0']['net'] for a in anc)/2, 1)}
        out[name] = res
    t = out['test']
    gn, lo = t['gann']['1.0']['net'], t['gann_ci95_expectancy_cost1'][0]
    if gn > 0 and lo > 0 and gn > t['control_vol']['1.0']['net'] and gn > t['control_anchor_net_cost1']['p95']:
        verdict = 'SUCCESS'
    elif gn <= 0 or gn <= t['control_vol']['1.0']['net'] or gn <= t['control_anchor_net_cost1']['median']:
        verdict = 'FAILURE'
    else:
        verdict = 'INCONCLUSIVE'
    out['verdict'] = verdict
    return out


if __name__ == '__main__':
    json.dump(run(), sys.stdout, indent=1)
