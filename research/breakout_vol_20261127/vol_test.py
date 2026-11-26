"""Breakout detector volume cut: robustness on untouched data + two pre-registered variants (2026-11-27).

Frozen rule = research/filters_20261124/squeeze.py events(N=6, K=6, H=12, T=1.5, tick 0.01, vol_conf=True).
events2() is that function plus `vmult` (volume cut, 1.5 = live rule) and `align` (break must agree with the sign of
prior close minus session open); with defaults it returns exactly what events() returns (asserted below).
Choice of variant: SPY 5m train sessions 1-40 ONLY. Then judged once on: SPY test (41-60), 10 large stocks over the
same dates (other instruments), and the same stocks on sessions after 2026-11-13 (never seen by any earlier research).
Inputs: ./fetch_data.sh. Run from this folder: python vol_test.py > result.txt
"""
import glob, random, sys
REPO = '../..'
import json, gzip, math, statistics as st, datetime as dt
from zoneinfo import ZoneInfo
NY = ZoneInfo("America/New_York")

def load_yahoo(path):
    r = json.load(gzip.open(path))['chart']['result'][0]; q = r['indicators']['quote'][0]; out = []
    for i, t in enumerate(r['timestamp']):
        v = [q[k][i] for k in ('open', 'high', 'low', 'close')]
        if None in v: continue
        x = dt.datetime.fromtimestamp(t, NY)
        if not (dt.time(9, 30) <= x.time() < dt.time(16, 0)): continue
        out.append((x, *v, (q.get('volume') or [None]*len(r['timestamp']))[i] or 0))
    return out

def atr20(B, i):
    return sum(max(B[j][2]-B[j][3], abs(B[j][2]-B[j-1][4]), abs(B[j][3]-B[j-1][4])) for j in range(i-19, i+1)) / 20

def events(B, N, K, H, T, tick, vol_conf, cut=None, ratios_only=False, start=dt.time(10, 0), last=dt.time(15, 0)):
    out, ratios = [], []
    i = 25
    day = [b[0].date() for b in B]
    while i < len(B) - 1:
        if day[i-21] != day[i] or not (start <= B[i][0].time() <= last):
            i += 1; continue
        box = B[i-N+1:i+1]; hi = max(b[2] for b in box); lo = min(b[3] for b in box); a = atr20(B, i)
        r = (hi - lo) / a if a > 0 else None
        if r is None: i += 1; continue
        if ratios_only: ratios.append(r); i += 1; continue
        if cut is not None and r > cut: i += 1; continue
        # wait for a break within K bars
        done = False
        for j in range(i+1, min(i+1+K, len(B))):
            if day[j] != day[i]: break
            up, dn = B[j][2] > hi, B[j][3] < lo
            if up and dn: break                                    # both sides in one bar: skip (ambiguous)
            if not (up or dn): continue
            if vol_conf:
                vols = [b[5] for b in B[j-20:j]]
                if not sum(vols) or B[j][5] < 1.5 * sum(vols) / 20: break
            d = 1 if up else -1
            e = (hi + tick) if up else (lo - tick)
            risk = (e - lo + tick) if up else (hi + tick - e)
            stop, tgt = e - d*risk, e + d*T*risk
            R = None
            # the entry bar itself: if it also reaches the stop -> loss
            if (B[j][3] <= stop) if d > 0 else (B[j][2] >= stop): R = -1.0
            elif (B[j][2] >= tgt) if d > 0 else (B[j][3] <= tgt): R = T
            k = j
            while R is None:
                k += 1
                if k >= len(B) or day[k] != day[i] or k > j + H:
                    px = B[k-1][4]; R = d*(px - e)/risk; break
                hs, ht = ((B[k][3] <= stop), (B[k][2] >= tgt)) if d > 0 else ((B[k][2] >= stop), (B[k][3] <= tgt))
                if hs: R = -1.0
                elif ht: R = T
            out.append(dict(t=B[i][0], d=d, R=R, risk=risk))
            i = k; done = True
            break
        if not done: i += 1
    return ratios if ratios_only else out

def summ(ev):
    if len(ev) < 2: return dict(n=len(ev))
    R = [e['R'] for e in ev]; m = st.mean(R); se = st.stdev(R)/math.sqrt(len(R))
    return dict(n=len(R), win=round(100*sum(r > 0 for r in R)/len(R)), avgR=round(m, 3), ci=(round(m-1.96*se, 3), round(m+1.96*se, 3)))


def events2(B, N, K, H, T, tick, vol_conf, cut=None, ratios_only=False, start=dt.time(10, 0), last=dt.time(15, 0), vmult=1.5, align=False):
    out, ratios = [], []
    i = 25
    day = [b[0].date() for b in B]
    while i < len(B) - 1:
        if day[i-21] != day[i] or not (start <= B[i][0].time() <= last):
            i += 1; continue
        box = B[i-N+1:i+1]; hi = max(b[2] for b in box); lo = min(b[3] for b in box); a = atr20(B, i)
        r = (hi - lo) / a if a > 0 else None
        if r is None: i += 1; continue
        if ratios_only: ratios.append(r); i += 1; continue
        if cut is not None and r > cut: i += 1; continue
        # wait for a break within K bars
        done = False
        for j in range(i+1, min(i+1+K, len(B))):
            if day[j] != day[i]: break
            up, dn = B[j][2] > hi, B[j][3] < lo
            if up and dn: break                                    # both sides in one bar: skip (ambiguous)
            if not (up or dn): continue
            if vol_conf:
                vols = [b[5] for b in B[j-20:j]]
                if not sum(vols) or B[j][5] < vmult * sum(vols) / 20: break
            d = 1 if up else -1
            if align:
                k0 = j
                while k0 > 0 and day[k0-1] == day[j]: k0 -= 1
                if d * (B[j-1][4] - B[k0][1]) <= 0: break   # prior close vs session open disagrees with the break
            e = (hi + tick) if up else (lo - tick)
            risk = (e - lo + tick) if up else (hi + tick - e)
            stop, tgt = e - d*risk, e + d*T*risk
            R = None
            # the entry bar itself: if it also reaches the stop -> loss
            if (B[j][3] <= stop) if d > 0 else (B[j][2] >= stop): R = -1.0
            elif (B[j][2] >= tgt) if d > 0 else (B[j][3] <= tgt): R = T
            k = j
            while R is None:
                k += 1
                if k >= len(B) or day[k] != day[i] or k > j + H:
                    px = B[k-1][4]; R = d*(px - e)/risk; break
                hs, ht = ((B[k][3] <= stop), (B[k][2] >= tgt)) if d > 0 else ((B[k][2] >= stop), (B[k][3] <= tgt))
                if hs: R = -1.0
                elif ht: R = T
            out.append(dict(t=B[i][0], d=d, R=R, risk=risk))
            i = k; done = True
            break
        if not done: i += 1
    return ratios if ratios_only else out



SYMS = ['AAPL', 'AMZN', 'AVGO', 'BRK-B', 'GOOGL', 'JPM', 'META', 'MSFT', 'NVDA', 'TSLA']
CUT = dt.date(2026, 11, 13)   # last session of the SPY data the live rule was chosen on


def merged(sym):
    files = [f'{REPO}/research/breadth_20261109/raw/{sym}_5m_60d.json.gz'] + sorted(glob.glob(f'data/snap/*_{sym}_5m.json.gz'))
    bars = {}
    for f in files:
        for b in load_yahoo(f):
            bars[b[0]] = b   # later snapshot wins on the same timestamp
    return [bars[k] for k in sorted(bars)]


def day_ci(ev, n=4000, seed=1):
    """Bootstrap over sessions: trades on the same day are correlated across stocks."""
    days = {}
    for e in ev: days.setdefault(e['t'].date(), []).append(e['R'])
    keys, rnd, m = list(days), random.Random(seed), []
    for _ in range(n):
        s = [r for k in (rnd.choice(keys) for _ in keys) for r in days[k]]; m.append(sum(s)/len(s))
    m.sort(); return round(m[int(.025*n)], 3), round(m[int(.975*n)], 3)


def run(B, vol=True, **kw): return events2(B, 6, 6, 12, 1.5, 0.01, vol, **kw)


spy = load_yahoo('data/SPY_5m_60d.json.gz')
stocks = {s: merged(s) for s in SYMS}
assert run(spy) == events(spy, 6, 6, 12, 1.5, 0.01, True) and run(spy, False) == events(spy, 6, 6, 12, 1.5, 0.01, False)
days = sorted({b[0].date() for b in spy}); split = days[40]
SETS = {'SPY train': lambda vol, kw: run([b for b in spy if b[0].date() < split], vol, **kw),
        'SPY test': lambda vol, kw: run([b for b in spy if b[0].date() >= split], vol, **kw),
        'stocks <=11-13': lambda vol, kw: [e for s in SYMS for e in run([b for b in stocks[s] if b[0].date() <= CUT], vol, **kw)],
        'stocks >11-13 (new)': lambda vol, kw: [e for s in SYMS for e in run([b for b in stocks[s] if b[0].date() > CUT], vol, **kw)]}
print('SPY', days[0], '..', days[-1], '| train < ', split, '| stocks', min(b[0].date() for b in stocks['AAPL']), '..', max(b[0].date() for b in stocks['AAPL']))
print('\n1) Is the volume filter real? (live rule, never tuned on stocks)')
for vol in (True, False):
    for k in ('stocks <=11-13', 'stocks >11-13 (new)'):
        ev = SETS[k](vol, {}); print(f"  {'vol 1.5x ' if vol else 'no volume'} {k:20s} {summ(ev)} dayCI={day_ci(ev)}")
print('\n2) Pre-registered variants (choice on SPY train only)')
V = {'live 1.5x': {}, 'H1 2.0x': dict(vmult=2.0), 'H2 session direction': dict(align=True)}
res = {v: {k: SETS[k](True, kw) for k in SETS} for v, kw in V.items()}
for v in V:
    print(' ', v); [print(f'     {k:20s} {summ(ev)}' + (f' dayCI={day_ci(ev)}' if k.startswith('stocks') else '')) for k, ev in res[v].items()]
best = max(V, key=lambda v: summ(res[v]['SPY train'])['avgR'])
beats = {k: summ(res[best][k])['avgR'] > summ(res['live 1.5x'][k])['avgR'] for k in SETS if k != 'SPY train'}
print(f'\nchosen on train: {best}; beats live on every held-out set: {all(beats.values())} {beats}')
print('\n3) Diagnostic only (not used for the choice): volume cut sweep, all sessions')
for vm in (1.5, 1.75, 2.0, 2.5, 3.0):
    a = summ(run(spy, vmult=vm)); b = summ([e for s in SYMS for e in run(stocks[s], vmult=vm)])
    print(f"  {vm}x  SPY n={a['n']:3d} avgR {a['avgR']:+.3f} | stocks n={b['n']:4d} avgR {b['avgR']:+.3f}")
