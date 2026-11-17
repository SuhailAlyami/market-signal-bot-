"""Pre-open direction from the overnight gap. Proxy for the pre-open futures-implied level: today's SPX open.
Direction call: sign(open - prev_close) when |gap| >= t*m, else 'up' (base rate). Truth: sign(close - prev_close).
t chosen on 2010-2019 only; accuracy reported on untouched 2020+ vs always-up. Also anchored levels from the open."""
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
    if abs(O - pc) < 1e-6:  # Yahoo sometimes stores open = prev close (no real open): unusable for this proxy
        continue
    m = pc*vix[a][3]/100/math.sqrt(252)
    rows.append(dict(d=b, g=(O-pc)/m, up=C > pc, O=O, H=H, L=L, m=m, pc=pc))
tr = [r for r in rows if r['d'] < '2020']; te = [r for r in rows if r['d'] >= '2020']
def acc(rs, t):
    call = [(r['g'] > 0) if abs(r['g']) >= t else True for r in rs]
    return sum(c == r['up'] for c, r in zip(call, rs))/len(rs)
best = max([0, .05, .1, .15, .2, .3, .4, .5], key=lambda t: acc(tr, t))
print('n_train', len(tr), 'n_test', len(te), 'chosen t', best)
print('always-up  train %.3f test %.3f' % (acc(tr, 99), acc(te, 99)))
print('gap rule   train %.3f test %.3f' % (acc(tr, best), acc(te, best)))
for lo, hi in ((-9, -.5), (-.5, -.2), (-.2, -.05), (-.05, .05), (.05, .2), (.2, .5), (.5, 9)):
    s = [r for r in te if lo <= r['g'] < hi]
    print(f'gap/m in [{lo},{hi}): n={len(s):4d}  P(close>prev)={sum(r["up"] for r in s)/len(s):.2f}')
# levels from the open (test period), what fraction reach open +- k*m
for k in (0.1, 0.25):
    print('from open k=%.2f  high reach %.3f  low reach %.3f' % (k, sum(r['H'] >= r['O']+k*r['m'] for r in te)/len(te), sum(r['L'] <= r['O']-k*r['m'] for r in te)/len(te)))
print('first/last test day', te[0]['d'], te[-1]['d'])
print('-- close vs OPEN (what a trade entered at the open earns), test period')
for lo, hi in ((-9, -.5), (-.5, -.2), (-.2, .2), (.2, .5), (.5, 9)):
    s = [r for r in te if lo <= r['g'] < hi]
    co = [spx[r['d']][3] > r['O'] for r in s]
    print(f'gap/m in [{lo},{hi}): n={len(s):4d}  P(close>open)={sum(co)/len(s):.2f}')
