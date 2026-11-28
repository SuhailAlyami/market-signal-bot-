"""Pre-registered (no tuning). SPX Dukascopy 1m 2025-01..2026-11, regular hours. Cost 0.5 pt per trade.
T1 Gao-Han-Li-Zhou intraday momentum: sign(prev close -> 10:00) ; trade 15:30 -> 15:59 close.
T2 sign(prev close -> 10:00) ; trade 10:00 -> 15:59 close.
T3 = T2 only on explosion-risk 'high' days (walk-forward model from exp.py: each year fit on earlier years, top-decile
   threshold from training-period predictions).
T4 sign(09:30 open -> 10:30) (first-hour direction) ; trade 10:30 -> close, all days and high-risk days.
Baseline: always long over the same window."""
import gzip, csv, glob, os, sys, math, statistics as st, json
from datetime import datetime
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); P, RISK = sys.argv[1], json.load(open(sys.argv[2]))
def load(f):
    b = {}
    for r in csv.DictReader(gzip.open(f, 'rt')):
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY); m = t.hour*60+t.minute
        if 570 <= m < 960: b[m] = (float(r['Open']), float(r['Close']))
    return b
days = []
for f in sorted(glob.glob(f'{P}/*.csv.gz')):
    b = load(f)
    if all(k in b for k in (570, 599, 600, 630, 929, 959)): days.append((os.path.basename(f)[:10], b))
rows = []
for (d0, b0), (d, b) in zip(days, days[1:]):
    pc = b0[959][1]; p10 = b[599][1]; p1030 = b[629][1]; o = b[570][0]; c = b[959][1]
    rows.append(dict(d=d, s1=1 if p10 > pc else -1, s4=1 if p1030 > o else -1, last30=b[959][1]-b[929][1],
                     rest=c-p10, rest4=c-p1030, high=RISK.get(d, False)))
def rep(name, xs):
    for lab, sel in (('2025', lambda r: r['d'] < '2026'), ('2026', lambda r: r['d'] >= '2026')):
        v = [p for r, p in xs if sel(r)]
        if len(v) < 5: print(f'{name:30s} {lab}: n={len(v)}'); continue
        m = st.mean(v); se = st.pstdev(v)/math.sqrt(len(v))
        print(f'{name:30s} {lab}: n={len(v):3d} win {100*sum(p > 0 for p in v)/len(v):3.0f}% avg {m:+6.2f} pts CI [{m-1.96*se:+6.2f},{m+1.96*se:+6.2f}] total {sum(v):+7.0f}')
c = 0.5
rep('T1 10:00 sign -> last 30m', [(r, r['s1']*r['last30']-c) for r in rows])
rep('   always long last 30m', [(r, r['last30']-c) for r in rows])
rep('T2 10:00 sign -> to close', [(r, r['s1']*r['rest']-c) for r in rows])
rep('   always long 10:00->close', [(r, r['rest']-c) for r in rows])
rep('T3 T2 on high-risk days', [(r, r['s1']*r['rest']-c) for r in rows if r['high']])
rep('T4 1st-hour sign -> close', [(r, r['s4']*r['rest4']-c) for r in rows])
rep('T4 on high-risk days', [(r, r['s4']*r['rest4']-c) for r in rows if r['high']])
print('high-risk days in sample', sum(r['high'] for r in rows), 'of', len(rows))
