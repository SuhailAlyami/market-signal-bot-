"""Failure analysis, random-timing baseline and validation sizing for control vs opening-seeded detector.
Runs on the 116 CONSUMED sessions: everything here is in-sample/descriptive, not out-of-sample evidence."""
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run_seed import (SPLIT, as_sessions, detect, detect_seeded, load_sessions, match_legs,  # noqa: E402
                      reference_legs, seeds_for)

DRAWS, SEED, MIN_GAP = 500, 901, 6


def bucket(i):
    return 'first40m' if i < 8 else ('40m-90m' if i < 18 else 'after90m')


def random_signals(rng, n_bars, k, first):
    """k uniformly random decision bars at >= first, spaced by the 30m cooldown, random side."""
    for _ in range(200):
        picks = sorted(rng.sample(range(first, n_bars), k)) if k <= n_bars-first else []
        if all(b-a >= MIN_GAP for a, b in zip(picks, picks[1:])):
            return [{'index': i, 'side': rng.choice((1, -1))} for i in picks]
    return [{'index': i, 'side': rng.choice((1, -1))} for i in sorted(rng.sample(range(first, n_bars), min(k, n_bars-first)))]


def summarize_legs(legs):
    return {'early': sum(l['early'] for l in legs), 'matched': sum(l['matched'] for l in legs), 'legs': len(legs)}


def main():
    loaded, _ = load_sessions(HERE.parent/'opening_validation_raw.json.gz')
    sessions = as_sessions(loaded)
    seeds = seeds_for([(d, b) for d, _, _, _, b in sessions])
    blocks = {'older': lambda d: d < SPLIT, 'recent': lambda d: d >= SPLIT, 'all': lambda d: True}
    per = {}
    for day, _, _, _, bars in sessions:
        legs = reference_legs(bars)
        arms = {'control': detect(bars), 'seeded': detect_seeded(bars, seeds[day])}
        per[day] = {'bars': bars, 'legs': legs, 'arms': arms,
                    'matched': {a: match_legs(bars, s, legs) for a, s in arms.items()}}

    report = {'scope': 'CONSUMED 116 sessions; descriptive/in-sample', 'failure_analysis': {}, 'random_baseline': {}, 'sizing': {}}
    # --- failure analysis: where do early matches and unmatched signals come from, per block
    for name, keep in blocks.items():
        days = [d for d in per if keep(d)]
        fa = {}
        for arm in ('control', 'seeded'):
            early_by, legs_by, unmatched_by = {}, {}, {}
            for d in days:
                legs = per[d]['matched'][arm]
                used = {l['signal_index'] for l in legs if l['matched']}
                for l in legs:
                    b = bucket(l['start'])
                    legs_by[b] = legs_by.get(b, 0)+1
                    early_by[b] = early_by.get(b, 0)+l['early']
                for s in per[d]['arms'][arm]:
                    if s['index'] not in used:
                        unmatched_by[bucket(s['index'])] = unmatched_by.get(bucket(s['index']), 0)+1
            fa[arm] = {'legs_by_start': legs_by, 'early_by_leg_start': early_by, 'unmatched_signals_by_decision_time': unmatched_by}
        gained = lost = 0
        for d in days:
            for c, s in zip(per[d]['matched']['control'], per[d]['matched']['seeded']):
                gained += (not c['early']) and s['early']
                lost += c['early'] and not s['early']
        fa['early_flips_control_to_seeded'] = {'gained': gained, 'lost': lost}
        report['failure_analysis'][name] = fa

    # --- random-timing baseline: same number of signals per session, same cooldown, random time and side
    rng = random.Random(SEED)
    for name, keep in blocks.items():
        days = [d for d in per if keep(d)]
        out = {}
        for arm, first in (('control', 7), ('seeded', 1)):
            actual = summarize_legs([l for d in days for l in per[d]['matched'][arm]])
            draws = []
            for _ in range(DRAWS):
                tot = {'early': 0, 'matched': 0}
                for d in days:
                    sig = random_signals(rng, len(per[d]['bars']), len(per[d]['arms'][arm]), first)
                    r = summarize_legs(match_legs(per[d]['bars'], sig, per[d]['legs']))
                    tot['early'] += r['early']; tot['matched'] += r['matched']
                draws.append(tot)
            for key in ('early', 'matched'):
                v = sorted(x[key] for x in draws)
                out[f'{arm}_{key}'] = {'actual': actual[key], 'random_mean': round(statistics.mean(v), 2),
                                       'random_p2.5_p97.5': [v[int(.025*DRAWS)], v[int(.975*DRAWS)-1]],
                                       'draws_ge_actual': sum(x >= actual[key] for x in v), 'draws': DRAWS}
        out['no_signal_baseline'] = {'early': 0, 'matched': 0}
        report['random_baseline'][name] = out

    # --- validation sizing from event counts (control arm early-match rate, session-clustered)
    days = list(per)
    e = [sum(l['early'] for l in per[d]['matched']['control']) for d in days]
    n_l = [len(per[d]['legs']) for d in days]
    p = sum(e)/sum(n_l)
    resid = [ei-p*li for ei, li in zip(e, n_l)]
    s2, mean_l = statistics.variance(resid), statistics.mean(n_l)
    se1 = math.sqrt(s2/len(days))/mean_l
    diff = [sum(l['early'] for l in per[d]['matched']['seeded'])-ei for d, ei in zip(days, e)]
    sd_d, mean_d = statistics.stdev(diff), statistics.mean(diff)
    report['sizing'] = {
        'sessions_in_sample': len(days), 'legs_per_session': round(mean_l, 3), 'control_early_rate': round(p, 4),
        'cluster_se_of_rate_116_sessions': round(se1, 4),
        'sessions_for_rate_half_width': {str(h): math.ceil((1.96**2)*s2/(mean_l**2*h**2)) for h in (.10, .075, .05)},
        'expected_legs_at_20_sessions': round(20*mean_l, 1),
        'rate_half_width_at_20_sessions': round(1.96*math.sqrt(s2/20)/mean_l, 4),
        'paired_diff_seeded_minus_control_per_session': {'mean': round(mean_d, 4), 'sd': round(sd_d, 4)},
        'sessions_for_80pct_power_if_true_gain_equals': {
            str(g): math.ceil(((1.96+.8416)*sd_d/g)**2) for g in (round(mean_d, 3), round(mean_d/2, 3))},
        'caveat': 'Effect size taken from the consumed sample that selected the change (winner-curse); recent block gain was 0. '
                  'Clustered-by-session; leg definitions retrospective. Targets, not proof.'}
    json.dump(report, sys.stdout, indent=1)


if __name__ == '__main__':
    main()
