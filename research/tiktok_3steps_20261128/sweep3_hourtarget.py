"""TikTok '3 steps' (qimatrade): 1H liquidity sweep -> 15M confirmation -> 5M order-block entry, R:R 1:2.
Mechanical rules fixed BEFORE running (no tuning). SPX = Dukascopy US500 1m, regular session 09:30-16:00 NY.
Hours anchored at 09:30 (09:30-10:30 ... 15:30-16:00 dropped as incomplete).
1H: hour H2 sweeps H1 low (low2 < low1) and closes back inside H1 (low1 <= close2 <= high1) -> LONG (mirror -> SHORT).
    If it sweeps both sides, skip.
15M: after H2 closes, within 120 min, a 15m candle k2 sweeps the previous 15m candle's low (long) and closes back
     above that low -> confirmation. 15m candles anchored at 09:30.
5M: order block = last bearish 5m candle (close<open) among the 5m candles of the confirmation 15m candle (long; mirror).
    If none, skip. Entry = limit at OB high (long) after confirmation; stop = confirmation candle's sweep low; target = entry+2R.
    Limit valid 60 min. Exit at 15:59 close if neither hit. Same-minute stop+target = stop. One trade per day max.
Cost: 0.5 pt round trip. Baselines: (a) same entries, opposite direction, same R logic; (b) random time/direction trades
with the same risk distance distribution, 2R target, seed fixed."""
import gzip, csv, glob, os, sys, random, statistics as st, math
from datetime import datetime
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); P = sys.argv[1]
def load(f):
    out = []
    for r in csv.DictReader(gzip.open(f, 'rt')):
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY)
        m = t.hour*60+t.minute
        if 570 <= m < 960: out.append((m, float(r['Open']), float(r['High']), float(r['Low']), float(r['Close'])))
    return out
def agg(bars, start, size):
    g = {}
    for b in bars:
        k = (b[0]-start)//size
        if k < 0: continue
        g.setdefault(k, []).append(b)
    return [(k, v[0][0], v[0][1], max(x[2] for x in v), min(x[3] for x in v), v[-1][4], v) for k, v in sorted(g.items()) if len(v) >= size*0.8]
def sim(bars, t0, entry, stop, d, valid=60, cost=0.5, tgt=None):
    """limit entry after minute t0; returns R or None (not filled)."""
    R = abs(entry-stop); tgt = tgt if tgt is not None else entry + d*2*R; filled = False
    for m, o, h, l, c in bars:
        if m <= t0: continue
        if not filled:
            if m > t0+valid: return None
            if (d > 0 and l <= entry) or (d < 0 and h >= entry):
                filled = True
                # same bar may also hit stop
                if (d > 0 and l <= stop) or (d < 0 and h >= stop): return -1 - cost/R
            continue
        if (d > 0 and l <= stop) or (d < 0 and h >= stop): return -1 - cost/R
        if (d > 0 and h >= tgt) or (d < 0 and l <= tgt): return d*(tgt-entry)/R - cost/R
        last = c
    if not filled: return None
    return d*(bars[-1][4]-entry)/R - cost/R
res = {'rule': [], 'flip': []}; risks = []; days = []
files = sorted(glob.glob(f'{P}/*.csv.gz'))
for f in files:
    day = os.path.basename(f)[:10]; bars = load(f)
    if len(bars) < 350: continue
    days.append((day, bars))
    H = agg(bars, 570, 60); Q = agg(bars, 570, 15)
    done = False
    for i in range(1, len(H)):
        if done: break
        _, t1, o1, h1, l1, c1, _ = H[i-1]; _, t2, o2, h2, l2, c2, _ = H[i]
        if H[i][0] != H[i-1][0]+1: continue
        lo = l2 < l1 and l1 <= c2 <= h1; sh = h2 > h1 and l1 <= c2 <= h1
        if lo == sh: continue
        d = 1 if lo else -1; hend = t2+60
        for j in range(1, len(Q)):
            k1, k2 = Q[j-1], Q[j]
            if k2[1] < hend or k2[1] >= hend+120: continue
            if d > 0 and not (k2[4] < k1[4] and k2[5] > k1[4]): continue
            if d < 0 and not (k2[3] > k1[3] and k2[5] < k1[3]): continue
            fives = agg(k2[6], k2[1], 5)
            ob = [x for x in fives if (x[5] < x[2]) == (d > 0)]
            if not ob: break
            ob = ob[-1]; entry = ob[3] if d > 0 else ob[4]; stop = k2[4] if d > 0 else k2[3]
            if (entry - stop)*d <= 0.5: break
            t0 = k2[1]+14
            r = sim(bars, t0, entry, stop, d, tgt=(h1 if d > 0 else l1))
            if r is not None:
                res['rule'].append((day, r)); risks.append(abs(entry-stop))
                # flip: same entry, mirrored stop/target distance
                rf = sim(bars, t0, entry, entry + d*abs(entry-stop), -d)
                if rf is not None: res['flip'].append((day, rf))
            done = True; break
rng = random.Random(7); rnd = []
for day, bars in days:
    if rng.random() > len(res['rule'])/len(days): continue
    t0 = rng.randrange(630, 900); d = rng.choice((1, -1)); R = rng.choice(risks)
    px = [b for b in bars if b[0] == t0]
    if not px: continue
    e = px[0][4]; r = sim(bars, t0-1, e, e - d*R, d, valid=2)
    if r is not None: rnd.append((day, r))
def rep(name, xs):
    for lab, sel in (('2025', lambda d: d < '2026'), ('2026', lambda d: d >= '2026'), ('all', lambda d: True)):
        v = [r for d, r in xs if sel(d)]
        if not v: continue
        m = st.mean(v); se = st.pstdev(v)/math.sqrt(len(v))
        print(f'{name:6s} {lab}: n={len(v):3d} win {100*sum(r > 0 for r in v)/len(v):3.0f}%  avg {m:+.2f}R  95%CI [{m-1.96*se:+.2f}, {m+1.96*se:+.2f}]  total {sum(v):+.1f}R')
print('days', len(days), 'median risk pts', st.median(risks) if risks else None)
rep('rule', res['rule']); rep('flip', res['flip']); rep('random', rnd)
