"""Compression -> breakout detector with an OCO bracket. Box = high/low of the last N bars (bar i close, from 10:00 NY).
Compressed if box height / ATR20 <= q-quantile (cut taken on TRAIN only). Entry: stop order at box high (long) or box low
(short) on the first break within K bars; stop = other side of the box; target = entry + T x risk; exit at H bars after entry
or the session close. A bar touching both stop and target = loss. Slippage: 1 tick each way.
Selection on SPY 5m sessions 1-40; test on sessions 41-60 once; second test on untouched SPX 1m (10 sessions)."""
import json, gzip, math, statistics as st, datetime as dt, itertools, sys
sys.path.insert(0, 'research_filters')
from filters_test import load_yahoo, load_spx1m
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York')

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

spy = load_yahoo('data_history-20261114/history/SPY_5m_60d.json.gz')
days = sorted({b[0].date() for b in spy}); split = days[40]
tr = [b for b in spy if b[0].date() < split]; te = [b for b in spy if b[0].date() >= split]
print('SPY 5m train', days[0], '..', days[39], '| test', split, '..', days[-1])
grid = []
for N, q, vol, T in itertools.product((6, 12), (0.15, 0.3, 1.0), (False, True), (1.5, 2.0)):
    ratios = events(tr, N, 6, 12, T, 0.01, vol, ratios_only=True)
    cut = sorted(ratios)[int(q*len(ratios))-1] if q < 1 else None
    s = summ(events(tr, N, 6, 12, T, 0.01, vol, cut))
    grid.append(((N, q, vol, T, cut), s)); print('TRAIN', dict(N=N, q=q, vol=vol, T=T), s)
ok = [g for g in grid if g[1].get('n', 0) >= 30]
best = max(ok, key=lambda g: g[1]['avgR'])
N, q, vol, T, cut = best[0]
base = [g for g in grid if g[0][:2] == (N, 1.0) and g[0][2] == vol and g[0][3] == T][0][0]
print('\nCHOSEN', dict(N=N, q=q, vol=vol, T=T, cut=round(cut, 3) if cut else None))
print('TEST SPY 5m  detector :', summ(events(te, N, 6, 12, T, 0.01, vol, cut)))
print('TEST SPY 5m  baseline (same bracket, no compression filter):', summ(events(te, N, 6, 12, T, 0.01, vol, None)))
# second test: untouched SPX 1m. Scale the 5m box to minutes (N*5 bars), same compression quantile from its own first 3 sessions? No:
# use the TRAIN quantile q itself applied to SPX 1m ratios of the first 3 untouched sessions (a calibration-only slice), test on the other 7.
spx1, sd, consumed = load_spx1m()
fresh = [b for b in spx1 if b[0].date().isoformat() not in consumed]
fd = sorted({b[0].date() for b in fresh}); cal = [b for b in fresh if b[0].date() < fd[3]]; tst = [b for b in fresh if b[0].date() >= fd[3]]
if not vol:
    r1 = events(cal, N*5, 30, 60, T, 0.25, False, ratios_only=True)
    cut1 = sorted(r1)[int(q*len(r1))-1] if q < 1 else None
    print('TEST SPX 1m (7 untouched sessions) detector :', summ(events(tst, N*5, 30, 60, T, 0.25, False, cut1)))
    print('TEST SPX 1m baseline:', summ(events(tst, N*5, 30, 60, T, 0.25, False, None)))
else:
    print('SPX 1m has no volume: second test not possible for a volume-confirmed variant')
