"""'At least' levels for the day's high and low, calibrated on 2010-2019 (train), checked untouched on 2020+ (test).
m = prev_close*VIX_prev/100/sqrt(252). Anchors: prev close (pre-open, alert-safe) and today's open.
Level_hi = anchor + q_hi*m with q_hi = (1-p) quantile... i.e. P(H >= level) = p on train; same for low.
Fixed before running: p in {0.7, 0.8, 0.9}; report test coverage of high level, low level, and both."""
import gzip, json, math
from datetime import datetime, timezone
def load(s):
    r = json.loads(gzip.open(__import__('pathlib').Path(__file__).resolve().parent.parent/'volatility_premium_20261115'/f'{s}_1d.json.gz').read())['chart']['result'][0]; q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).date().isoformat(): [q[k][i] for k in ('open','high','low','close')]
            for i, t in enumerate(r['timestamp']) if None not in [q[k][i] for k in ('open','high','low','close')]}
spx, vix = load('GSPC'), load('VIX'); days = sorted(spx)
rows = []
for a, b in zip(days, days[1:]):
    if b < '2010-01-04' or a not in vix: continue
    pc = spx[a][3]; O, H, L, C = spx[b]
    if H - L <= 0 or abs(O - pc) < 1e-9 and False: continue
    m = pc*vix[a][3]/100/math.sqrt(252)
    rows.append(dict(d=b, pc=pc, O=O, H=H, L=L, C=C, m=m))
train = [r for r in rows if r['d'] < '2020']; test = [r for r in rows if r['d'] >= '2020']
def q(v, p): v = sorted(v); return v[int(p*(len(v)-1))]
out = {'n_train': len(train), 'n_test': len(test), 'test_last': test[-1]['d']}
for anchor in ('pc', 'O'):
    for p in (0.7, 0.8, 0.9):
        qh = q([(r['H']-r[anchor])/r['m'] for r in train], 1-p)   # P(H-anchor >= qh*m) = p
        ql = q([(r[anchor]-r['L'])/r['m'] for r in train], 1-p)
        hi = [r['H'] >= r[anchor]+qh*r['m'] for r in test]; lo = [r['L'] <= r[anchor]-ql*r['m'] for r in test]
        out[f'{anchor}_p{p}'] = {'k_high': round(qh, 3), 'k_low': round(ql, 3),
            'test_cov_high': round(sum(hi)/len(hi), 3), 'test_cov_low': round(sum(lo)/len(lo), 3),
            'test_cov_both': round(sum(a and b for a, b in zip(hi, lo))/len(hi), 3),
            'example_today_pts': None}
# direction base rates
out['up_close_vs_prev_train'] = round(sum(r['C'] > r['pc'] for r in train)/len(train), 3)
out['up_close_vs_prev_test'] = round(sum(r['C'] > r['pc'] for r in test)/len(test), 3)
out['close_above_open_test'] = round(sum(r['C'] > r['O'] for r in test)/len(test), 3)
print(json.dumps(out, indent=1))
print('k_m  P(high>=O+k)  P(low<=O-k)  P(either)  P(both)   [2020+ test, open anchor]')
for k in (0.1, 0.25, 0.5, 0.75, 1.0, 1.5):
    hi = [r['H'] >= r['O']+k*r['m'] for r in test]; lo = [r['L'] <= r['O']-k*r['m'] for r in test]; n = len(test)
    print(k, round(sum(hi)/n, 3), round(sum(lo)/n, 3), round(sum(a or b for a, b in zip(hi, lo))/n, 3), round(sum(a and b for a, b in zip(hi, lo))/n, 3))
