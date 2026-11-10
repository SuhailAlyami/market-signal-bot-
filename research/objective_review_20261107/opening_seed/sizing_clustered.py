"""Uncertainty of the control early-match rate vs number of sessions, with within-session and serial dependence.
In-sample (116 consumed sessions); sampling-distribution approximation, not a power guarantee."""
import gzip
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_seed import load_sessions  # noqa: E402

DRAWS, SEED, BLOCK = 4000, 1101, 5


def half_width(vals):
    v = sorted(vals)
    return (v[int(.975*len(v))-1]-v[int(.025*len(v))])/2


def main():
    days = [d for d, *_ in load_sessions(HERE.parent/'opening_validation_raw.json.gz')[0]]
    legs = json.loads(gzip.open(HERE/'results.json.gz').read())['legs']['control']
    e = {d: 0 for d in days}; l = {d: 0 for d in days}
    for x in legs:
        l[x['day']] += 1; e[x['day']] += x['early']
    es = {d: 0 for d in days}
    for x in json.loads(gzip.open(HERE/'results.json.gz').read())['legs']['seeded']:
        es[x['day']] += x['early']
    D = [es[d]-e[d] for d in days]
    E, L = [e[d] for d in days], [l[d] for d in days]
    p = sum(E)/sum(L)
    resid = [a-p*b for a, b in zip(E, L)]
    r1 = statistics.correlation(resid[:-1], resid[1:])
    per_leg_var = p*(1-p)
    icc_like = statistics.variance(resid)/(statistics.mean(L)*per_leg_var)  # design effect of session clustering
    rng = random.Random(SEED)
    out = {'sessions': len(days), 'legs': sum(L), 'p': round(p, 4), 'observed_paired_rate_diff': round(sum(D)/sum(L), 4), 'design_effect_session_clustering': round(icc_like, 3),
           'lag1_autocorr_of_session_residuals': round(r1, 3), 'by_n': {}}
    for n in (20, 30, 40, 54, 80, 116, 200, 300):
        ratios, bratios = [], []
        for _ in range(DRAWS):
            idx = [rng.randrange(len(days)) for _ in range(n)]
            ratios.append(sum(E[i] for i in idx)/max(1, sum(L[i] for i in idx)))
            idx = []
            while len(idx) < n:
                s0 = rng.randrange(len(days))
                idx += [(s0+j) % len(days) for j in range(BLOCK)]
            idx = idx[:n]
            bratios.append(sum(E[i] for i in idx)/max(1, sum(L[i] for i in idx)))
        paired = []
        for _ in range(DRAWS):
            idx = [rng.randrange(len(days)) for _ in range(n)]
            paired.append(sum(D[i] for i in idx)/max(1, sum(L[i] for i in idx)))
        naive = 1.96*math.sqrt(per_leg_var/(n*statistics.mean(L)))
        out['by_n'][n] = {'naive_iid_legs': round(naive, 4), 'session_bootstrap': round(half_width(ratios), 4),
                          'paired_seeded_minus_control_rate_halfwidth': round(half_width(paired), 4),
                          f'block{BLOCK}_bootstrap': round(half_width(bratios), 4)}
    json.dump(out, sys.stdout, indent=1)


if __name__ == '__main__':
    main()
