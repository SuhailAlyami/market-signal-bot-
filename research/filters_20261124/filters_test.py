"""Do the project's ICT/SMC filters catch moves? Causal signals at bar close; success = +2 ATR in the signal direction
before -1 ATR against, within H bars (owner's definition). Baseline = every bar, both directions (unconditional rate).
Filters (same logic as price_action_context.py / strategy_rules.py, 20-bar window):
  sweep    : wick beyond the 20-bar extreme, close back inside (UP = sell-side sweep -> long)
  fvg      : fresh 3-candle gap (low > high[-2] -> UP)
  sweep+fvg: sweep then same-direction FVG within the next 3 bars (ICT displacement after a sweep)
  prelevel : close within 0.2 ATR of the 20-bar high (long) / low (short) with relative volume >= 1.2 (volume data only)
"""
import json, gzip, math, sys, datetime as dt
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York')

def load_yahoo(path):
    r = json.load(gzip.open(path))['chart']['result'][0]; q = r['indicators']['quote'][0]; out = []
    for i, t in enumerate(r['timestamp']):
        v = [q[k][i] for k in ('open', 'high', 'low', 'close')]
        if None in v: continue
        x = dt.datetime.fromtimestamp(t, NY)
        if not (dt.time(9, 30) <= x.time() < dt.time(16, 0)): continue
        out.append((x, *v, (q.get('volume') or [None]*len(r['timestamp']))[i] or 0))
    return out

def load_spx1m():
    d = json.load(open('spxcol/sessions.json')); out = []
    for day in sorted(d):
        s = d[day]
        for line in s['csv'].strip().splitlines()[1:]:
            t, o, h, l, c = line.split(',')[:5]
            out.append((dt.datetime.fromisoformat(f'{day}T{t}').replace(tzinfo=NY), float(o), float(h), float(l), float(c), 0))
    return out, sorted(d), {k for k in d if d[k].get('consumed_in_prior_research')}

def signals(B, W=20):
    """Per session, causal: uses bars <= i only. Returns list of (i, name, direction)."""
    out = []
    day = [b[0].date() for b in B]
    for i in range(W + 2, len(B)):
        if day[i - W - 1] != day[i]: continue           # whole window inside the session
        o, h, l, c = B[i][1:5]
        prior = B[i - W:i]
        hi, lo = max(b[2] for b in prior), min(b[3] for b in prior)
        tr = [max(B[j][2] - B[j][3], abs(B[j][2] - B[j-1][4]), abs(B[j][3] - B[j-1][4])) for j in range(i - W + 1, i + 1)]
        atr = sum(tr) / W
        if atr <= 0: continue
        su, sd = l < lo and c > lo, h > hi and c < hi
        sweep = 1 if su and not sd else -1 if sd and not su else 0
        fvg = 1 if l > B[i-2][2] else -1 if h < B[i-2][3] else 0
        vols = [b[5] for b in prior]; rvol = (B[i][5] / (sum(vols) / W)) if sum(vols) > 0 else None
        out.append(dict(i=i, atr=atr, sweep=sweep, fvg=fvg, hi=hi, lo=lo, c=c, rvol=rvol))
    return out

def outcome(B, i, d, atr, H):
    """+1 win (2 ATR first), -1 loss (1 ATR first, or both in one bar), 0 timeout. Returns (code, R)."""
    e = B[i][4]; tp, sl = e + d * 2 * atr, e - d * atr
    last = e
    for j in range(i + 1, min(i + 1 + H, len(B))):
        if B[j][0].date() != B[i][0].date(): break
        h, l = B[j][2], B[j][3]
        hit_tp = h >= tp if d > 0 else l <= tp
        hit_sl = l <= sl if d > 0 else h >= sl
        if hit_sl: return -1, -1.0                       # conservative: a bar touching both counts as a loss
        if hit_tp: return 1, 2.0
        last = B[j][4]
    return 0, d * (last - e) / atr

def wilson(k, n, z=1.96):
    if n == 0: return (0, 1)
    p = k / n; d_ = 1 + z*z/n; c = (p + z*z/(2*n)) / d_; h = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / d_
    return c - h, c + h

def evaluate(B, H, label, sessions_note):
    S = signals(B)
    by_i = {s['i']: s for s in S}
    groups = {'baseline (every bar, both directions)': [], 'sweep': [], 'fvg': [], 'sweep+fvg': [], 'prelevel(rvol)': []}
    for s in S:
        i = s['i']
        for d in (1, -1): groups['baseline (every bar, both directions)'].append((i, d, s['atr']))
        if s['sweep']: groups['sweep'].append((i, s['sweep'], s['atr']))
        if s['fvg']: groups['fvg'].append((i, s['fvg'], s['atr']))
        if s['fvg']:
            for k in (1, 2, 3):
                p = by_i.get(i - k)
                if p and p['sweep'] == s['fvg'] and B[i-k][0].date() == B[i][0].date():
                    groups['sweep+fvg'].append((i, s['fvg'], s['atr'])); break
        if s['rvol'] is not None and s['rvol'] >= 1.2:
            if (s['hi'] - s['c']) / s['atr'] <= 0.2: groups['prelevel(rvol)'].append((i, 1, s['atr']))
            elif (s['c'] - s['lo']) / s['atr'] <= 0.2: groups['prelevel(rvol)'].append((i, -1, s['atr']))
    print(f'\n=== {label} | horizon {H} bars | {sessions_note}')
    base = None
    for name, ev in groups.items():
        if not ev: print(f'{name:40s} n=0'); continue
        res = [outcome(B, i, d, a, H) for i, d, a in ev]
        w = sum(r[0] == 1 for r in res); l_ = sum(r[0] == -1 for r in res); n = len(res)
        R = sum(r[1] for r in res) / n
        lo, hi = wilson(w, n)
        if base is None: base = w / n
        flag = ' <-- above baseline' if lo > base else (' (below baseline)' if hi < base else '')
        print(f'{name:40s} n={n:6d} win={100*w/n:5.1f}% [{100*lo:4.1f}-{100*hi:4.1f}] loss={100*l_/n:5.1f}% avgR={R:+.3f}{flag}')

spy = load_yahoo('data_history-20261114/history/SPY_5m_60d.json.gz')
gspc5 = load_yahoo('data_history-20261114/history/GSPC_5m_60d.json.gz')
n_spy = len({b[0].date() for b in spy})
evaluate(spy, 6, 'SPY 5m (with volume)', f'{n_spy} sessions {spy[0][0].date()}..{spy[-1][0].date()}')
evaluate(spy, 12, 'SPY 5m (with volume)', f'{n_spy} sessions')
evaluate(gspc5, 6, 'SPX index 5m (no volume)', f'{len({b[0].date() for b in gspc5})} sessions')
spx1, days, consumed = load_spx1m()
fresh = [b for b in spx1 if b[0].date().isoformat() not in consumed]
evaluate(fresh, 5, 'SPX 1m UNTOUCHED sessions (owner rule: 5 min)', f'{len({b[0].date() for b in fresh})} sessions never used in research')
evaluate(fresh, 15, 'SPX 1m UNTOUCHED sessions', f'15-minute horizon')
