"""Diagnosis from EXISTING retained outputs only (wave_capture results). No new detector, no sweep.
Consumed 116 sessions: findings are descriptive/in-sample, not independent validation."""
import gzip
import json
import random
import statistics as st
import sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]/'objective_review_20261107/wave_capture/results.json.gz'
d = json.loads(gzip.open(R).read())
legs, sig = d['reference_legs'], [s for s in d['signals'] if s['delay'] == 0 and s['status'] == 'SCORED']
q = lambda v, p: sorted(v)[min(len(v)-1, int(p*len(v)))]
out = {'scope': 'wave_capture control, 116 consumed sessions; descriptive'}

dur = [5*(l['end']-l['start']) for l in legs]
out['legs'] = {'n': len(legs), 'duration_min': {'p25': q(dur, .25), 'median': q(dur, .5), 'p75': q(dur, .75)},
               'share_duration_le_15': round(sum(x <= 15 for x in dur)/len(dur), 3),
               'share_duration_le_30': round(sum(x <= 30 for x in dur)/len(dur), 3),
               'share_duration_le_45': round(sum(x <= 45 for x in dur)/len(dur), 3),
               'median_points': round(st.median(l['points'] for l in legs), 1)}
m = [l for l in legs if l['matched']]
out['matched_legs'] = {'n': len(m), 'median_lag_min': st.median(l['lag_minutes'] for l in m),
                       'consumed_fraction_quartiles': [round(q([l['consumed_fraction'] for l in m], p), 3) for p in (.25, .5, .75)],
                       'share_consumed_le_25': round(sum(l['consumed_fraction'] <= .25 for l in m)/len(m), 3),
                       'share_consumed_25_50': round(sum(.25 < l['consumed_fraction'] <= .5 for l in m)/len(m), 3),
                       'share_consumed_50_75': round(sum(.5 < l['consumed_fraction'] <= .75 for l in m)/len(m), 3),
                       'median_remaining_points_after_signal': round(st.median(l['points']*(1-l['consumed_fraction']) for l in m), 1)}
# lag budget when the feed itself is late
for delay in (0, 5, 15):
    lag = out['matched_legs']['median_lag_min']+delay
    out['legs'][f'share_legs_shorter_than_median_lag_plus_{delay}min'] = round(sum(x <= lag for x in dur)/len(dur), 3)
# legs by session position (5m bar index)
b = {'first40m': 0, '40m-90m': 0, 'after90m': 0}
for l in legs:
    b['first40m' if l['start'] < 8 else '40m-90m' if l['start'] < 18 else 'after90m'] += 1
out['leg_starts'] = {k: {'n': v, 'share': round(v/len(legs), 3)} for k, v in b.items()}
out['leg_starts']['session_time_share'] = {'first40m': round(40/390, 3), '40m-90m': round(50/390, 3), 'after90m': round(300/390, 3)}

g = [s['gross_low'] for s in sig]
rr = [s['gross_low']/s['r'] for s in sig]
ex = {}
for s in sig:
    ex[s['exit']] = ex.get(s['exit'], 0)+1
days = sorted({s['day'] for s in sig})
by = {x: [s['gross_low'] for s in sig if s['day'] == x] for x in days}
rng = random.Random(1201)
boot = sorted(sum(sum(by[x]) for x in rng.choices(days, k=len(days)))/sum(len(by[x]) for x in days) for _ in range(2000))
out['execution_delay0'] = {'trades': len(sig), 'mean_gross_points': round(st.mean(g), 3),
                           'mean_gross_points_session_bootstrap95': [round(boot[49], 3), round(boot[1949], 3)],
                           'mean_gross_in_R': round(st.mean(rr), 4), 'median_R_points': round(st.median(s['r'] for s in sig), 2),
                           'cost_1pt_as_share_of_median_R': round(1/st.median(s['r'] for s in sig), 3),
                           'exit_counts': ex, 'target_share_of_stop_or_target': round(ex.get('target', 0)/(ex.get('target', 0)+ex.get('stop', 0)+ex.get('stop_gap', 0)), 3),
                           'breakeven_target_share_for_1R_stop_2R_target_zero_cost': 0.333,
                           'direction30_correct': round(sum(s['direction30_correct'] for s in sig)/len(sig), 3),
                           'median_window_mfe_over_R': round(st.median(s['window_mfe']/s['r'] for s in sig), 3),
                           'median_window_mae_over_R': round(st.median(s['window_mae']/s['r'] for s in sig), 3)}
order = sorted(range(len(sig)), key=lambda i: (sig[i]['r'], i))  # rank terciles; many R values tie at the 5-point floor
n = len(order)
tb = {}
for name, ids in (('low_R', order[:n//3]), ('mid_R', order[n//3:2*n//3]), ('high_R', order[2*n//3:])):
    sub = [sig[i] for i in ids]
    tb[name] = {'n': len(sub), 'R_range': [round(min(s['r'] for s in sub), 1), round(max(s['r'] for s in sub), 1)],
                'mean_gross_points': round(st.mean(s['gross_low'] for s in sub), 3),
                'mean_gross_in_R': round(st.mean(s['gross_low']/s['r'] for s in sub), 4),
                'net_cost1_points': round(sum(s['gross_low']-1 for s in sub), 1)}
out['by_R_tercile'] = tb
json.dump(out, sys.stdout, indent=1)
