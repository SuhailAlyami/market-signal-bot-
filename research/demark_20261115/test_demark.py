"""DeMark projected high/low on SPX daily, 2010-01-04 .. last bar. Rules fixed BEFORE looking at results:
X = H+2L+C if C<O; 2H+L+C if C>O; H+L+2C if C==O. Ph = X/2-L, Pl = X/2-H (from day t-1, applied to day t).
Compared estimators of day-t high/low: DeMark; naive prior-day H/L; VIX band prev_close +- C*VIX/100/sqrt(252);
prev_close +- half of 20-day average range. Metrics: mean abs error of high and of low (points), separately
for 2010-2019 and 2020+. Level test: on days the high reaches the level, % closing back below it (rejection),
DeMark Ph vs prior-day high (same for lows). Verdict 'useful' only if DeMark beats all baselines on MAE in both
periods, or its rejection rate beats the prior-day level by >= 5 points in both periods."""
import gzip, json, math, statistics as st
from datetime import datetime, timezone

def load(s):
    r = json.loads(gzip.open(__import__('pathlib').Path(__file__).resolve().parent.parent/'volatility_premium_20261115'/f'{s}_1d.json.gz').read())['chart']['result'][0]; q = r['indicators']['quote'][0]
    out = {}
    for i, t in enumerate(r['timestamp']):
        v = [q[k][i] for k in ('open', 'high', 'low', 'close')]
        if None not in v:
            out[datetime.fromtimestamp(t, timezone.utc).date().isoformat()] = v
    return out

spx, vix = load('GSPC'), load('VIX')
days = sorted(d for d in spx if d >= '2009-11-01')
rows = []
for k in range(21, len(days)):
    d, p = days[k], days[k-1]
    if d < '2010-01-04' or p not in vix:
        continue
    o, h, l, c = spx[p]; O, H, L, C = spx[d]
    if h - l <= 0:
        continue
    x = h+2*l+c if c < o else (2*h+l+c if c > o else h+l+2*c)
    m = c*vix[p][3]/100/math.sqrt(252)
    ar = st.mean(spx[days[j]][1]-spx[days[j]][2] for j in range(k-20, k))
    est = {'demark': (x/2-l, x/2-h), 'prior_hl': (h, l), 'vix_band': (c+m, c-m), 'avg_range': (c+ar/2, c-ar/2)}
    rows.append({'d': d, 'H': H, 'L': L, 'C': C, 'O': O, 'est': est, 'ph': x/2-l, 'pl': x/2-h, 'h': h, 'l': l})

def period(r): return '2010-2019' if r['d'] < '2020' else '2020+'
res = {'first': rows[0]['d'], 'last': rows[-1]['d'], 'n': len(rows), 'mae': {}, 'levels': {}}
for per in ('2010-2019', '2020+'):
    sub = [r for r in rows if period(r) == per]
    res['mae'][per] = {k: {'high': round(st.mean(abs(r['est'][k][0]-r['H']) for r in sub), 1),
                           'low': round(st.mean(abs(r['est'][k][1]-r['L']) for r in sub), 1)} for k in rows[0]['est']}
    lv = {}
    for name, hi, lo in (('demark', 'ph', 'pl'), ('prior_hl', 'h', 'l')):
        up = [r for r in sub if r['H'] >= r[hi]]; dn = [r for r in sub if r['L'] <= r[lo]]
        lv[name] = {'high_touched_pct': round(100*len(up)/len(sub), 1), 'high_reject_pct': round(100*st.mean(r['C'] < r[hi] for r in up), 1),
                    'low_touched_pct': round(100*len(dn)/len(sub), 1), 'low_reject_pct': round(100*st.mean(r['C'] > r[lo] for r in dn), 1)}
    res['levels'][per] = lv
    res.setdefault('n_by_period', {})[per] = len(sub)
beats = all(res['mae'][p]['demark'][s] < min(res['mae'][p][k][s] for k in res['mae'][p] if k != 'demark')
            for p in res['mae'] for s in ('high', 'low'))
rej = all(res['levels'][p]['demark'][f'{s}_reject_pct'] - res['levels'][p]['prior_hl'][f'{s}_reject_pct'] >= 5
          for p in res['levels'] for s in ('high', 'low'))
res['verdict'] = 'USEFUL' if (beats or rej) else 'NOT_BETTER_THAN_BASELINES'
print(json.dumps(res, indent=1))
