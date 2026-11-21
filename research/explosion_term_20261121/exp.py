"""Pre-registered variants vs current explosion model. Same target/walk-forward (test years 2020..2026, fit on earlier years)."""
import json, sys, math, numpy as np
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, '/home/user/market-signal-bot-/range_alert')
import explosion as X
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
D = sys.argv[1]; NY = ZoneInfo('America/New_York')
def load(s):
    r = json.load(open(f'{D}/{s}.json'))['chart']['result'][0]; q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat(): (q['open'][i], q['high'][i], q['low'][i], q['close'][i])
            for i, t in enumerate(r['timestamp']) if None not in (q['open'][i], q['high'][i], q['low'][i], q['close'][i])}
spx = load('%5EGSPC'); spx.pop('2026-11-21', None)
c = {s: {d: v[3] for d, v in load(s).items()} for s in ('%5EVIX', '%5EVIX9D', '%5EVIX3M', '%5EVVIX', '%5ESKEW')}
vix = c['%5EVIX']
data = X.dataset(spx, vix)
days = sorted(d for d in spx if d in vix)
prev = {days[i]: days[i-1] for i in range(1, len(days))}
rows = []
for d, f, e, m in data:
    p = prev[d]
    ex = [c[s].get(p) for s in ('%5EVIX9D', '%5EVIX3M', '%5EVVIX', '%5ESKEW')]
    if None in ex: continue
    v = vix[p]
    rows.append((d, f, [ex[0]/v, v/ex[1], ex[2], ex[3]], e))
print('n', len(rows), rows[0][0], rows[-1][0])
F = np.array([r[1] for r in rows]); E = np.array([r[2] for r in rows]); y = np.array([r[3] for r in rows]).astype(int)
yr = np.array([int(r[0][:4]) for r in rows]); dd = [r[0] for r in rows]
base = F; term = np.c_[F, E[:, :2]]; allx = np.c_[F, E]
def wf(Xm, kind='lr', first=2020):
    p = np.full(len(y), np.nan)
    for Y in range(first, yr.max()+1):
        tr, te = yr < Y, yr == Y
        mu, sd = Xm[tr].mean(0), Xm[tr].std(0)+1e-12
        mdl = LogisticRegression(max_iter=3000) if kind == 'lr' else HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, random_state=7)
        mdl.fit((Xm[tr]-mu)/sd, y[tr]); p[te] = mdl.predict_proba((Xm[te]-mu)/sd)[:, 1]
    return p
te = yr >= 2020; yt = y[te]
res = {}
for name, Xm, k in (('base_lr', base, 'lr'), ('term_lr', term, 'lr'), ('all_lr', allx, 'lr'), ('base_gb', base, 'gb'), ('all_gb', allx, 'gb')):
    p = wf(Xm, k)[te]; res[name] = p
    q = np.quantile(p, .9); top = p >= q
    print(f'{name:8s} AUC {roc_auc_score(yt, p):.3f} top10 {yt[top].mean():.3f} ({yt[top].sum()}/{yt.sum()}) rest {yt[~top].mean():.3f}')
print('base rate test', yt.mean().round(3), 'n', len(yt))
rng = np.random.default_rng(1)
for name in res:
    if name == 'base_lr': continue
    diffs = []
    for _ in range(1000):
        i = rng.integers(0, len(yt), len(yt))
        if yt[i].min() == yt[i].max(): continue
        diffs.append(roc_auc_score(yt[i], res[name][i]) - roc_auc_score(yt[i], res['base_lr'][i]))
    print(f'{name} - base AUC diff 95% CI [{np.quantile(diffs,.025):+.3f}, {np.quantile(diffs,.975):+.3f}]')
# recent days
idx = np.where(te)[0]
for nm in ('base_lr', 'term_lr', 'all_lr'):
    q = np.quantile(res[nm], .9)
    print(nm, ' '.join(f"{dd[i][5:]}:{res[nm][j]:.2f}{'*' if res[nm][j]>=q else ''}{'E' if y[i] else ''}" for j, i in enumerate(idx) if dd[i] >= '2026-11-10'))
print('--- per year AUC base / term, top10 hit base / term')
for Y in range(2020, yr.max()+1):
    m = yr[te] == Y
    a = [roc_auc_score(yt[m], res[n][m]) for n in ('base_lr', 'term_lr')]
    h = []
    for n in ('base_lr', 'term_lr'):
        q = np.quantile(res[n], .9); h.append(yt[m & (res[n] >= q)].mean())
    print(Y, m.sum(), f'{a[0]:.3f} {a[1]:.3f} | {h[0]:.2f} {h[1]:.2f}')
for nm, cols in (('vix9d_only', [0]), ('vix3m_only', [1])):
    p = wf(np.c_[F, E[:, cols]])[te]; q = np.quantile(p, .9)
    print(nm, f'AUC {roc_auc_score(yt, p):.3f} top10 {yt[p>=q].mean():.3f}')
