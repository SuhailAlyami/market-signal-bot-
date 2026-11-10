"""Volatility-state gate screen (protocol.json). Reuses wave_capture engine unchanged; consumed sessions only."""
import hashlib
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent/'objective_review_20261107'
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT/'wave_capture'))
from objective_review import RIYADH, load_sessions  # noqa: E402
from run import aggregate5, detect, score, SPLIT  # noqa: E402

GATE = 5.0


def main():
    rows = []  # one per signal, both sides scored at delay 0
    for day, raw, _, step, closing in load_sessions(ROOT/'opening_validation_raw.json.gz')[0]:
        for s in detect(aggregate5(raw, step)):
            both = {side: score(raw, step, closing, s, side, 0) for side in (1, -1)}
            if all(v['status'] == 'SCORED' for v in both.values()):
                rows.append({'day': day, 'r': s['r'], 'side': s['side'], 'both': both})
    own = lambda x: x['both'][x['side']]['gross_low']
    days = sorted({x['day'] for x in rows})
    blocks = {'older': [d for d in days if d < SPLIT], 'recent': [d for d in days if d >= SPLIT], 'all': days}
    gated = [x for x in rows if x['r'] > GATE]
    floor = [x for x in rows if x['r'] <= GATE]

    def summ(sub):
        g = [own(x) for x in sub]
        return {'n': len(sub), 'mean_gross_points': round(st.mean(g), 3), 'mean_gross_in_R': round(st.mean(own(x)/x['r'] for x in sub), 4),
                'net': {str(c): round(sum(v-c for v in g), 1) for c in (.5, 1, 2)}}
    out = {'scope': 'consumed 116 sessions, delay 0, both sides scoreable; development screen not validation',
           'protocol_sha256': hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest(), 'blocks': {}}
    for name, ds in blocks.items():
        k = set(ds)
        out['blocks'][name] = {'gated': summ([x for x in gated if x['day'] in k]), 'floor_bound': summ([x for x in floor if x['day'] in k]),
                               'ungated': summ([x for x in rows if x['day'] in k])}

    # C2: gated minus floor-bound mean gross in R, session-cluster bootstrap
    by = defaultdict(lambda: {'g': [], 'f': []})
    for x in rows:
        by[x['day']]['g' if x['r'] > GATE else 'f'].append(own(x)/x['r'])
    rng = random.Random(1302)
    diffs = []
    for _ in range(2000):
        pick = rng.choices(days, k=len(days))
        g = [v for d in pick for v in by[d]['g']]
        f = [v for d in pick for v in by[d]['f']]
        if g and f:
            diffs.append(st.mean(g)-st.mean(f))
    diffs.sort()
    point = st.mean(v for d in days for v in by[d]['g'])-st.mean(v for d in days for v in by[d]['f'])
    c2 = {'point': round(point, 4), 'bootstrap95': [round(diffs[int(.025*len(diffs))], 4), round(diffs[int(.975*len(diffs))-1], 4)]}

    # C3: within-session random direction permutation among gated signals (cost 1)
    gd = defaultdict(list)
    for x in gated:
        gd[x['day']].append(x)
    prng = random.Random(1301)
    exp_day = {d: 0.0 for d in days}
    for _ in range(1000):
        for d in days:
            sides = [x['side'] for x in gd[d]]
            prng.shuffle(sides)
            exp_day[d] += sum(x['both'][s]['gross_low']-1 for x, s in zip(gd[d], sides))/1000
    act = {d: sum(own(x)-1 for x in gd[d]) for d in days}
    delta = [act[d]-exp_day[d] for d in days]
    brng = random.Random(1303)
    boot = sorted(sum(brng.choices(delta, k=len(delta))) for _ in range(1000))
    c3 = {'candidate_minus_mean_permutation_points': round(sum(delta), 2), 'bootstrap95': [round(boot[24], 2), round(boot[974], 2)],
          'permutation_mean_net': round(sum(exp_day.values()), 2)}

    ob = out['blocks']
    checks = {'C1_gross_positive_both_blocks': ob['older']['gated']['mean_gross_points'] > 0 and ob['recent']['gated']['mean_gross_points'] > 0,
              'C2_state_dependence_lower_gt_0': c2['bootstrap95'][0] > 0,
              'C3_beats_permutation_lower_gt_0': c3['bootstrap95'][0] > 0,
              'C4_gated_net_cost1_positive': ob['all']['gated']['net']['1'] > 0}
    out.update(C2=c2, C3=c3, checks=checks,
               decision='ADVANCE_TO_FROZEN_PROSPECTIVE_TEST_ONLY' if all(checks.values()) else 'STOP_THIS_HYPOTHESIS')
    json.dump(out, sys.stdout, indent=1)


if __name__ == '__main__':
    main()
