"""FROZEN breadth screen logic (protocol.json, commit fc4f002). Do not edit.

Signal source (wave_capture.detect), the agreement measure, scoring, seeds and criteria C1-C4 are moved here
verbatim from the original run.py; only input loading and date selection live elsewhere (inputs.py).
"""
import hashlib
import importlib.util
import json
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent/'objective_review_20261107'
sys.path.insert(0, str(ROOT))
_spec = importlib.util.spec_from_file_location('wave_capture_run', ROOT/'wave_capture'/'run.py')
_wave = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_wave)
aggregate5, detect, score = _wave.aggregate5, _wave.detect, _wave.score

P = json.loads((HERE/'protocol.json').read_text())
UNIVERSE = P['universe']
DEV_SCOPE = 'development sessions only (< 2026-11-05); SPX outcomes previously consumed; breadth feature new'


def agreement(closes, decision, side):
    at = decision-timedelta(minutes=5)       # start of decision bar; its close is the decision close
    prev = at-timedelta(minutes=15)          # bar t-3
    if any(at not in closes[u] or prev not in closes[u] for u in UNIVERSE):
        return None
    return sum((closes[u][at]/closes[u][prev]-1)*side > 0 for u in UNIVERSE)


def signal_rows(sessions, closes, scored=True):
    """Rows per signal. With scored=False no outcome is computed (used for outcome-free event counting)."""
    rows, dropped = [], 0
    for day, raw, _, step, closing in sessions:
        for s in detect(aggregate5(raw, step)):
            agree = agreement(closes, s['decision'], s['side'])
            if agree is None:
                dropped += 1
                continue
            if not scored:
                rows.append({'day': day, 'side': s['side'], 'agree': agree})
                continue
            both = {side: score(raw, step, closing, s, side, 0) for side in (1, -1)}
            if all(v['status'] == 'SCORED' for v in both.values()):
                rows.append({'day': day, 'side': s['side'], 'r': s['r'], 'agree': agree, 'both': both})
    return rows, dropped


def evaluate(sessions, excluded, closes, scope=DEV_SCOPE):
    rows, dropped = signal_rows(sessions, closes)
    own = lambda x: x['both'][x['side']]['gross_low']
    days = sorted({d for d, *_ in sessions})
    mid = days[len(days)//2]
    hi = [x for x in rows if x['agree'] >= 8]
    rest = [x for x in rows if x['agree'] <= 7]

    def summ(sub):
        if not sub:
            return {'n': 0}
        g = [own(x) for x in sub]
        return {'n': len(sub), 'mean_gross': round(st.mean(g), 3),
                'dir30_correct': round(st.mean(x['both'][x['side']]['direction30_correct'] for x in sub), 3),
                'net': {str(c): round(sum(v-c for v in g), 1) for c in (.5, 1, 2)}}
    out = {'scope': scope,
           'protocol_sha256': hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(),
           'sessions': len(days), 'first_day': days[0], 'last_day': days[-1], 'excluded_sessions': excluded,
           'signals_dropped_missing_constituent_bars': dropped,
           'agreement_histogram': {k: sum(x['agree'] == k for x in rows) for k in range(11)},
           'all': summ(rows), 'high': summ(hi), 'rest': summ(rest),
           'high_first_half': summ([x for x in hi if x['day'] < mid]), 'high_second_half': summ([x for x in hi if x['day'] >= mid])}

    by = defaultdict(lambda: {'h': [], 'r': []})
    for x in rows:
        by[x['day']]['h' if x['agree'] >= 8 else 'r'].append(own(x))
    rng = random.Random(1401)
    diffs = []
    for _ in range(2000):
        pick = rng.choices(days, k=len(days))
        h = [v for d in pick for v in by[d]['h']]; r = [v for d in pick for v in by[d]['r']]
        if h and r:
            diffs.append(st.mean(h)-st.mean(r))
    diffs.sort()
    c1 = {'point': round(st.mean(own(x) for x in hi)-st.mean(own(x) for x in rest), 3) if hi and rest else None,
          'bootstrap95': [round(diffs[int(.025*len(diffs))], 3), round(diffs[int(.975*len(diffs))-1], 3)]}
    gd = defaultdict(list)
    for x in hi:
        gd[x['day']].append(x)
    prng = random.Random(1402)
    exp = {d: 0.0 for d in days}
    for _ in range(1000):
        for d in days:
            sides = [x['side'] for x in gd[d]]
            prng.shuffle(sides)
            exp[d] += sum(x['both'][s]['gross_low']-1 for x, s in zip(gd[d], sides))/1000
    delta = [sum(own(x)-1 for x in gd[d])-exp[d] for d in days]
    brng = random.Random(1403)
    boot = sorted(sum(brng.choices(delta, k=len(delta))) for _ in range(1000))
    c4 = {'high_minus_random_direction_net_cost1': round(sum(delta), 2), 'bootstrap95': [round(boot[24], 2), round(boot[974], 2)]}
    checks = {'C1_high_minus_rest_lower_gt_0': c1['bootstrap95'][0] > 0,
              'C2_high_net_cost1_positive': out['high'].get('net', {}).get('1', -1) > 0,
              'C3_high_gross_positive_both_halves': all(out[k].get('mean_gross', -1) > 0 for k in ('high_first_half', 'high_second_half')),
              'C4_high_beats_random_direction_lower_gt_0': c4['bootstrap95'][0] > 0}
    out.update(C1=c1, C4=c4, checks=checks, decision='ADVANCE_TO_LOCKED_HOLDOUT' if all(checks.values()) else 'REJECT')
    out['_rows'] = rows  # removed by callers before printing; kept for the forward-only C5 check
    return out
