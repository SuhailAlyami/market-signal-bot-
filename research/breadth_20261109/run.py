"""Breadth screen entry point.

Default: development run (dates < 2026-11-05); output is byte-identical to the original result.json.
--forward STORE: the pre-registered forward test (forward_protocol.json). It counts high-agreement events
without computing any outcome and refuses to score until the pre-registered minimum is reached (no interim looks).
"""
import argparse
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from breadth_core import UNIVERSE, aggregate5, detect, evaluate, score, signal_rows  # noqa: E402,F401
from inputs import HOLDOUT_FROM, NY, bars_of, dev_inputs, forward_inputs  # noqa: E402,F401

FP = json.loads((HERE/'forward_protocol.json').read_text())


def spx_sessions():  # kept for audit.py compatibility
    sessions, excluded, _ = dev_inputs()
    return sessions, excluded


def block_bootstrap_c5(rows, days, block=5, draws=4000, seed=1501):
    own = lambda x: x['both'][x['side']]['gross_low']
    by = defaultdict(lambda: {'h': [], 'r': []})
    for x in rows:
        by[x['day']]['h' if x['agree'] >= 8 else 'r'].append(own(x))
    rng = random.Random(seed)
    vals = []
    for _ in range(draws):
        pick = []
        while len(pick) < len(days):
            s0 = rng.randrange(len(days)); pick += [days[(s0+j) % len(days)] for j in range(block)]
        h = [v for d in pick[:len(days)] for v in by[d]['h']]; r = [v for d in pick[:len(days)] for v in by[d]['r']]
        if h and r:
            vals.append(st.mean(h)-st.mean(r))
    vals.sort()
    return {'block': block, 'bootstrap95': [round(vals[int(.025*len(vals))], 3), round(vals[int(.975*len(vals))-1], 3)]}


def forward_decision(checks):
    return 'FORWARD_PASS_STILL_NOT_READY' if all(checks.values()) else 'FORWARD_FAIL'


def run_forward(store, start=HOLDOUT_FROM, end=None, allow_consumed=False):
    sessions, excluded, closes = forward_inputs(store, start, end, allow_consumed)
    count_rows, _ = signal_rows(sessions, closes, scored=False)
    high = sum(x['agree'] >= 8 for x in count_rows)
    need = FP['minimum_high_agreement_events']
    status = {'synchronized_sessions': len(sessions), 'excluded_days': excluded, 'high_agreement_events': high,
              'required_high_agreement_events': need}
    if high < need:
        return dict(status, status='NOT_ENOUGH_EVENTS_NO_OUTCOMES_COMPUTED')
    out = evaluate(sessions, excluded, closes, scope='FORWARD sessions >= 2026-11-05 (untouched until this single run)')
    rows = out.pop('_rows')
    c5 = block_bootstrap_c5(rows, sorted({d for d, *_ in sessions}))
    checks = dict(out['checks'], C5_block5_bootstrap_lower_gt_0=c5['bootstrap95'][0] > 0)
    out.update(status, C5=c5, checks=checks, decision=forward_decision(checks))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--forward', type=Path, help='collector store breadth5m/bars5m.json')
    a = p.parse_args()
    if a.forward:
        json.dump(run_forward(a.forward), sys.stdout, indent=1)
    else:
        out = evaluate(*dev_inputs())
        out.pop('_rows')
        json.dump(out, sys.stdout, indent=1)
