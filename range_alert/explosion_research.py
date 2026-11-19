"""Research script kept for reproducibility (reads GSPC/VIX daily json.gz from branch research/volatility-premium-20261115)."""
"""Can an 'explosion day' be flagged before the open? Fixed before running.
m = prev_close*VIX_prev/100/sqrt(252). Targets: A) |close-open| >= 0.75m (strong trend from the open);
B) high-low >= 1.5m (very wide day). Pre-open features only (today's open = proxy for the pre-open futures level):
gap/m, |gap|/m, VIX_prev, VIX 1d % change, VIX/RV21, prior range/m, prior |C-O|/m, mean range/m over 5 and 20 days,
prior day sign, weekday. Models: logistic regression and gradient boosting, fit on 2010-2019, scored on 2020+ only.
Report AUC, and hit rate in the top 10% / 20% of predicted risk vs the base rate. Direction on flagged days:
does sign(gap) give sign(close-open)?"""
import gzip, json, math, statistics as st
from datetime import datetime, timezone, date
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score
def load(s):
    r = json.loads(gzip.open(f'{s}.json.gz').read())['chart']['result'][0]; q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).date().isoformat(): [q[k][i] for k in ('open','high','low','close')]
            for i, t in enumerate(r['timestamp']) if None not in [q[k][i] for k in ('open','high','low','close')]}
spx, vix = load('GSPC'), load('VIX'); days = [d for d in sorted(spx) if d in vix]
X, YA, YB, meta = [], [], [], []
for k in range(25, len(days)):
    d, p = days[k], days[k-1]
    if d < '2010-01-04': continue
    O, H, L, C = spx[d]; po, ph, pl, pc = spx[p]
    if abs(O - pc) < 1e-6: continue
    v = vix[p][3]; m = pc*v/100/math.sqrt(252)
    px = [spx[days[j]][3] for j in range(k-22, k)]
    rv = math.sqrt(sum(math.log(b/a)**2 for a, b in zip(px, px[1:]))*252/21)*100
    rng = lambda j: (spx[days[j]][1]-spx[days[j]][2])/m
    g = (O-pc)/m
    X.append([g, abs(g), v, 100*(v/vix[days[k-2]][3]-1), v/rv, (ph-pl)/m, abs(pc-po)/m,
              st.mean(rng(j) for j in range(k-5, k)), st.mean(rng(j) for j in range(k-20, k)),
              1 if pc > spx[days[k-2]][3] else 0, date.fromisoformat(d).weekday()])
    YA.append(abs(C-O) >= .75*m); YB.append(H-L >= 1.5*m); meta.append((d, g, C-O))
X, YA, YB = np.array(X), np.array(YA), np.array(YB)
tr = np.array([d < '2020' for d, *_ in meta]); te = ~tr
print(f'train {tr.sum()} test {te.sum()} | base rate A train {YA[tr].mean():.3f} test {YA[te].mean():.3f} | B train {YB[tr].mean():.3f} test {YB[te].mean():.3f}')
for tname, Y in (('A |C-O|>=0.75m', YA), ('B range>=1.5m', YB)):
    for mname, model in (('logit', make_pipeline(StandardScaler(), LogisticRegression(max_iter=2000))),
                         ('gboost', HistGradientBoostingClassifier(max_depth=3, max_iter=200, learning_rate=0.05, random_state=7))):
        model.fit(X[tr], Y[tr]); p = model.predict_proba(X[te])[:, 1]; y = Y[te]
        order = np.argsort(-p); out = []
        for q in (.1, .2):
            top = order[:int(q*len(p))]; out.append(f'top{int(q*100)}% hit {y[top].mean():.2f} (catches {y[top].sum()}/{y.sum()})')
        print(f'{tname:15s} {mname:6s} AUC {roc_auc_score(y, p):.3f} | ' + ' | '.join(out) + f' | base {y.mean():.2f}')
        if tname.startswith('A') and mname == 'logit':
            top = order[:int(.2*len(p))]
            mt = [meta[i] for i in np.where(te)[0][top]]
            big = [x for x in mt if abs(x[1]) >= 0.2]
            same = sum((x[1] > 0) == (x[2] > 0) for x in big)
            print(f'   direction on flagged days with |gap|>=0.2m: gap sign = intraday sign {same}/{len(big)}')
