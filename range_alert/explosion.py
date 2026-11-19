"""Pre-open 'explosion day' risk for SPX: probability that |close - open| >= 0.75 m today, where
m = prev_close * VIX_prev / 100 / sqrt(252). Logistic model on 11 pre-open features (gap from the implied open,
VIX level and change, VIX vs realized vol, recent ranges). Inference is pure Python; training needs numpy +
scikit-learn and runs monthly (walk-forward: each test year is predicted by a model fit only on earlier years).
Research basis: 2010-2019 fit, 2020-2026 untouched: top-10% risk days 35-37% explosions vs 21% base."""
import json
import math
import statistics as st
from datetime import date

K_EXPLODE = 0.75
FEATURES = ['gap', 'abs_gap', 'vix', 'vix_chg', 'vix_rv', 'prev_range', 'prev_body', 'range5', 'range20', 'prev_up', 'weekday']


def features(day, rows, vix, anchor=None):
    """rows: ordered list of (iso_day, open, high, low, close) of completed sessions before `day` (>= 22 rows);
    vix: {iso_day: close}. anchor = today's open (training) or implied open from futures (live)."""
    p, pp = rows[-1], rows[-2]
    pc, v = p[4], vix[p[0]]
    m = pc*v/100/math.sqrt(252)
    px = [r[4] for r in rows[-22:]]
    rv = math.sqrt(sum(math.log(b/a)**2 for a, b in zip(px, px[1:]))*252/21)*100
    rng = lambda r: (r[2]-r[3])/m
    g = (anchor-pc)/m
    f = [g, abs(g), v, 100*(v/vix[pp[0]]-1), v/rv, (p[2]-p[3])/m, abs(p[4]-p[1])/m,
         st.mean(rng(r) for r in rows[-5:]), st.mean(rng(r) for r in rows[-20:]), 1 if pc > pp[4] else 0,
         date.fromisoformat(day).weekday()]
    return f, m


def prob(model, f):
    z = model['intercept'] + sum(c*(x-mu)/sd for c, x, mu, sd in zip(model['coef'], f, model['mean'], model['std']))
    return 1/(1+math.exp(-max(-50.0, min(50.0, z))))


def tier(model, p):
    """(key, Arabic label, observed out-of-sample explosion rate %) for probability p."""
    for t in model['tiers']:
        if p >= t['min_p']:
            return t['key'], t['label'], t['rate']
    return 'normal', 'عادي', model['base_rate']


def dataset(spx, vix):
    """spx: {iso: (o,h,l,c)}, vix: {iso: close}. Yields (day, features, exploded, m)."""
    days = [d for d in sorted(spx) if d in vix]
    out = []
    for k in range(25, len(days)):
        d, pc = days[k], spx[days[k-1]][3]
        o, h, l, c = spx[d]
        if abs(o-pc) < 1e-6:           # Yahoo sometimes stores open = prev close: unusable as the gap proxy
            continue
        rows = [(x, *spx[x]) for x in days[k-25:k]]
        f, m = features(d, rows, vix, anchor=o)
        out.append((d, f, abs(c-o) >= K_EXPLODE*m, m))
    return out


def train(spx, vix, first_test_year=2020):
    """Walk-forward out-of-sample evaluation, then a final model on all data. Returns the model dict."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import roc_auc_score
    data = dataset(spx, vix)
    X = np.array([f for _, f, _, _ in data]); y = np.array([e for _, _, e, _ in data]); yr = np.array([int(d[:4]) for d, *_ in data])
    def fit(Xa, ya):
        mu, sd = Xa.mean(0), Xa.std(0)+1e-12
        lr = LogisticRegression(max_iter=2000).fit((Xa-mu)/sd, ya)
        return mu, sd, lr
    oos_p, oos_y = [], []
    for Y in range(first_test_year, yr.max()+1):
        tr, te = yr < Y, yr == Y
        if te.sum() == 0:
            continue
        mu, sd, lr = fit(X[tr], y[tr])
        oos_p += list(lr.predict_proba((X[te]-mu)/sd)[:, 1]); oos_y += list(y[te])
    oos_p, oos_y = np.array(oos_p), np.array(oos_y)
    q90 = float(np.quantile(oos_p, .9))
    rate = lambda mask: round(100*float(oos_y[mask].mean()))
    mu, sd, lr = fit(X, y)
    return {'features': FEATURES, 'k_explode': K_EXPLODE, 'mean': mu.tolist(), 'std': sd.tolist(),
            'coef': lr.coef_[0].tolist(), 'intercept': float(lr.intercept_[0]),
            # Only the top decile separated out of sample (80-90th pct was no better than the rest on 2020-2026).
            'tiers': [{'key': 'high', 'label': 'مرتفع', 'min_p': q90, 'rate': rate(oos_p >= q90)}],
            'base_rate': rate(oos_p < q90), 'overall_rate': round(100*float(oos_y.mean())),
            'oos': {'from': f'{first_test_year}-01-01', 'to': data[-1][0], 'n': int(len(oos_y)),
                    'auc': round(float(roc_auc_score(oos_y, oos_p)), 3)},
            'trained_through': data[-1][0], 'n_train': int(len(y))}


def yahoo_daily(symbol, start='2009-10-01'):
    """Daily OHLC of completed sessions (today's partial bar excluded). range=max would downsample, so use periods."""
    import time as _t
    from daily_range import yahoo_chart
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    p1 = int(datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp())
    r = yahoo_chart(symbol, f'interval=1d&period1={p1}&period2={int(_t.time())}')
    q = r['indicators']['quote'][0]
    ny = ZoneInfo('America/New_York')
    today = datetime.now(ny).date().isoformat()
    out = {datetime.fromtimestamp(t, timezone.utc).astimezone(ny).date().isoformat(): (q['open'][i], q['high'][i], q['low'][i], q['close'][i])
           for i, t in enumerate(r['timestamp']) if None not in (q['open'][i], q['high'][i], q['low'][i], q['close'][i])}
    out.pop(today, None)
    return out


if __name__ == '__main__':
    import sys
    spx = yahoo_daily('^GSPC')
    vix = {d: v[3] for d, v in yahoo_daily('^VIX').items()}
    model = train(spx, vix)
    out = sys.argv[1] if len(sys.argv) > 1 else 'range_alert/explosion_model.json'
    open(out, 'w').write(json.dumps(model, indent=1, ensure_ascii=False)+'\n')
    print(json.dumps({k: model[k] for k in ('oos', 'tiers', 'base_rate', 'overall_rate', 'trained_through')}, ensure_ascii=False))
