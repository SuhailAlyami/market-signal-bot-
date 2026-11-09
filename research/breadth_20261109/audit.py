"""Validity audit of the frozen breadth screen. Reads only development dates (< 2026-11-05). No thresholds changed."""
import gzip
import json
import math
import random
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
import importlib.util  # noqa: E402
_spec = importlib.util.spec_from_file_location('breadth_run', HERE/'run.py')  # frozen screen, reused unchanged
B = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(B)

out = {}

# 1. timestamp semantics and alignment: 5m bar labels vs 1m bars (overlapping development days only)
r5 = json.loads(gzip.open(HERE/'raw/GSPC_5m_60d.json.gz').read())['chart']['result'][0]
r1 = json.loads(gzip.open(sys.argv[1]).read())['chart']['result'][0]
NY = B.NY
def series(r):
    q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).astimezone(NY): (q['open'][i], q['high'][i], q['low'][i], q['close'][i])
            for i, t in enumerate(r['timestamp']) if q['close'][i] is not None}
s5, s1 = series(r5), series(r1)
checked = mism_start = mism_end = 0
for at, (o, h, l, c) in s5.items():
    d = at.date().isoformat()
    if not ('2026-10-29' <= d < B.HOLDOUT_FROM) or at.hour == 16:
        continue
    mins = [at+timedelta(minutes=k) for k in range(5)]
    if all(m in s1 for m in mins):
        checked += 1
        start_ok = abs(s1[mins[0]][0]-o) < 1e-6 and abs(s1[mins[-1]][3]-c) < 1e-6 and \
            abs(max(s1[m][1] for m in mins)-h) < 1e-6 and abs(min(s1[m][2] for m in mins)-l) < 1e-6
        mism_start += not start_ok
        prev = [at-timedelta(minutes=k) for k in range(1, 6)]
        if all(m in s1 for m in prev):
            mism_end += abs(s1[prev[-1]][0]-o) < 1e-6 and abs(s1[prev[0]][3]-c) < 1e-6
out['timestamp_alignment'] = {
    'meaning': 'chart timestamp = bar START (interval [t, t+5m)); meta.regularMarketTime = time of the last regular-market quote update as stamped by Yahoo; neither is a delivery/receipt latency',
    'bars_checked_against_1m': checked, 'mismatch_if_start_label': mism_start, 'matches_if_end_label': mism_end}

# 2/4. constituent grid completeness, nulls, zero-volume / flat bars in development window
comp = {}
for u in ['^GSPC']+B.UNIVERSE:
    r = json.loads(gzip.open(HERE/'raw'/f"{u.replace('^', '')}_5m_60d.json.gz").read())['chart']['result'][0]
    q = r['indicators']['quote'][0]
    days = defaultdict(int); nulls = zero_vol = flat = 0
    for i, t in enumerate(r['timestamp']):
        at = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
        if at.date().isoformat() >= B.HOLDOUT_FROM or not (9*60+30 <= at.hour*60+at.minute < 16*60):
            continue
        if q['close'][i] is None:
            nulls += 1; continue
        days[at.date().isoformat()] += 1
        zero_vol += (q['volume'][i] or 0) == 0 and u != '^GSPC'
        flat += q['high'][i] == q['low'][i]
    comp[u] = {'sessions': len(days), 'incomplete_sessions': sum(v != 78 for v in days.values()), 'null_bars': nulls,
               'zero_volume_bars': zero_vol, 'flat_bars': flat}
out['data_completeness'] = comp

# rebuild the frozen screen's rows (same code path) to audit availability, confounding and uncertainty
sessions, _ = B.spx_sessions()
closes = {s: {at: v[3] for at, v in B.bars_of(s).items()} for s in B.UNIVERSE}
rows = []
for day, raw, _, step, closing in sessions:
    bars = B.aggregate5(raw, step)
    for s in B.detect(bars):
        at = s['decision']-timedelta(minutes=5)
        prev = at-timedelta(minutes=15)
        agree = sum((closes[u][at]/closes[u][prev]-1)*s['side'] > 0 for u in B.UNIVERSE)
        res0 = B.score(raw, step, closing, s, s['side'], 0)
        res5 = B.score(raw, step, closing, s, s['side'], 5)
        i = s['index']
        spx_mom = s['side']*(bars[i].close-bars[i-3].close)/s['r'] if i >= 3 else None
        rows.append({'day': day, 'agree': agree, 'r': s['r'], 'entry_bar_start': None,
                     'g0': res0.get('gross_low') if res0['status'] == 'SCORED' else None,
                     'g5': res5.get('gross_low') if res5['status'] == 'SCORED' else None,
                     'spx_mom_R': spx_mom, 'decision': s['decision']})
# 3. entry after availability: engine enters at first raw bar with start >= decision (+delay)
ok = [x for x in rows if x['g0'] is not None]
hi = [x for x in ok if x['agree'] >= 8]; rest = [x for x in ok if x['agree'] <= 7]
out['entry_timing'] = {'rule': 'entry = open of first 5m bar starting at or after decision (= close of decision bar); no intrabar entry; assumes zero delivery delay',
                       'high_n': len(hi), 'high_mean_gross_delay0': round(st.mean(x['g0'] for x in hi), 3),
                       'rest_mean_gross_delay0': round(st.mean(x['g0'] for x in rest), 3)}
h5 = [x['g5'] for x in hi if x['g5'] is not None]; r5_ = [x['g5'] for x in rest if x['g5'] is not None]
out['entry_timing'].update(sensitivity_one_bar_later={'high_n': len(h5), 'high_mean_gross': round(st.mean(h5), 3),
                                                    'rest_mean_gross': round(st.mean(r5_), 3), 'diff': round(st.mean(h5)-st.mean(r5_), 3)})

# 5. confounding with SPX's own 15-min move (constituents are ~1/3 of the index)
m = [x for x in ok if x['spx_mom_R'] is not None]
ag, mo = [x['agree'] for x in m], [x['spx_mom_R'] for x in m]
corr = st.correlation(ag, mo)
srt = sorted(m, key=lambda x: x['spx_mom_R'])
strata = {}
for k, part in enumerate((srt[:len(srt)//3], srt[len(srt)//3:2*len(srt)//3], srt[2*len(srt)//3:])):
    h = [x['g0'] for x in part if x['agree'] >= 8]; r = [x['g0'] for x in part if x['agree'] <= 7]
    strata[f'spx_15m_aligned_move_tercile_{k+1}'] = {'n_high': len(h), 'n_rest': len(r),
        'diff_high_minus_rest': round(st.mean(h)-st.mean(r), 3) if h and r else None}
out['confounding_with_spx_momentum'] = {'corr_agreement_vs_spx_aligned_15m_move_in_R': round(corr, 3), 'within_strata': strata}

# 6. uncertainty: session bootstrap and 5-session block bootstrap of C1; one-sided bootstrap p
days = sorted({x['day'] for x in ok})
by = defaultdict(lambda: {'h': [], 'r': []})
for x in ok:
    by[x['day']]['h' if x['agree'] >= 8 else 'r'].append(x['g0'])
def diff(pick):
    h = [v for d in pick for v in by[d]['h']]; r = [v for d in pick for v in by[d]['r']]
    return st.mean(h)-st.mean(r) if h and r else None
rng = random.Random(1501)
sb = sorted(v for v in (diff(rng.choices(days, k=len(days))) for _ in range(4000)) if v is not None)
bb = []
for _ in range(4000):
    pick = []
    while len(pick) < len(days):
        s0 = rng.randrange(len(days)); pick += [days[(s0+j) % len(days)] for j in range(5)]
    v = diff(pick[:len(days)])
    if v is not None:
        bb.append(v)
bb.sort()
p_one = sum(v <= 0 for v in sb)/len(sb)
sd_h, sd_r = st.stdev(x['g0'] for x in hi), st.stdev(x['g0'] for x in rest)
iid_se = math.sqrt(sd_h**2/len(hi)+sd_r**2/len(rest))
boot_se = st.stdev(sb)
out['uncertainty'] = {'point': round(diff(days), 3), 'session_bootstrap95': [round(sb[int(.025*len(sb))], 3), round(sb[int(.975*len(sb))-1], 3)],
                      'block5_bootstrap95': [round(bb[int(.025*len(bb))], 3), round(bb[int(.975*len(bb))-1], 3)],
                      'one_sided_bootstrap_p': round(p_one, 4), 'iid_se': round(iid_se, 3), 'session_bootstrap_se': round(boot_se, 3),
                      'design_effect_var': round((boot_se/iid_se)**2, 3), 'sd_gross_high': round(sd_h, 2), 'sd_gross_rest': round(sd_r, 2)}

# 7. prior multiple testing
m_tests = int(sys.argv[2])
out['multiple_testing'] = {'preregistered_protocols_in_research': m_tests, 'bonferroni_adjusted_p': round(min(1, p_one*m_tests), 3),
                           'note': 'Protocols are not all on the same data or outcome; Bonferroni over them is a conservative bound, not an exact correction.'}

# validation target from event counts
rate_h = len(hi)/len(days); rate_r = len(rest)/len(days)
deff = (boot_se/iid_se)**2
tgt = {}
for delta in (round(diff(days), 2), round(diff(days)/2, 2)):
    n_h = ((1.96+0.8416)**2)*(sd_h**2+sd_r**2*rate_h/rate_r)/delta**2*deff  # high events needed (rest scales with rate)
    tgt[str(delta)] = {'high_events_needed': math.ceil(n_h), 'sessions_at_dev_rate': math.ceil(n_h/rate_h)}
out['validation_target'] = {'high_events_per_session': round(rate_h, 2), 'rest_events_per_session': round(rate_r, 2),
                            'for_80pct_power_two_sided_5pct_if_true_diff_equals': tgt,
                            'note': 'Observed diff is a best-case (selected) estimate; the halved diff is the planning case.'}
json.dump(out, sys.stdout, indent=1, default=str)
