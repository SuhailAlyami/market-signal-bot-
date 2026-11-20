"""Multi-timeframe 'expected' levels (pivot of the previous completed candle, (H+L+C)/3) on 15m, 1h and daily.
For each level active at a time, the first touch (price reaches it from one side) is a test: bounce if price moves
R points back away from the level before moving R through it, within 30 minutes. R = 5 points. Baseline: the same
procedure on a shifted level (pivot + 7.3 points), which has no meaning. Confluence = 15m and 1h pivots within 2 pts.
Dukascopy US500 1m RTH, 2025-01..2026-11-10."""
import csv, gzip, sys, statistics as st
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); R = 5.0
def load(p):
    out = []
    for r in csv.DictReader(gzip.open(p, 'rt')):
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY)
        hm = t.hour*60+t.minute
        if 570 <= hm <= 959: out.append((hm, float(r['High']), float(r['Low']), float(r['Close'])))
    return out
def pivots(bars, size):
    """pivot of the previous completed candle of `size` minutes, valid from each minute (RTH-aligned)."""
    piv = {}
    for hm, *_ in bars:
        start = 570 + ((hm-570)//size)*size; ps = start-size
        prev = [b for b in bars if ps <= b[0] < start]
        if len(prev) >= size*0.8:
            piv[hm] = (max(b[1] for b in prev)+min(b[2] for b in prev)+prev[-1][3])/3
    return piv
def test(bars, lvl_at, shift=0.0):
    res, used = [], set()
    for i in range(1, len(bars)-1):
        hm = bars[i][0]
        if hm not in lvl_at or hm > 930: continue
        L = round(lvl_at[hm]+shift, 1)
        if L in used: continue
        pc, (h, l, c) = bars[i-1][3], bars[i][1:]
        if not (l <= L <= h): continue
        used.add(L); side = 1 if pc > L else -1          # approached from above -> support (expect up)
        out = None
        for b in bars[i+1:i+31]:
            if (b[1] >= L+R if side > 0 else b[2] <= L-R): out = True; break
            if (b[2] <= L-R if side > 0 else b[1] >= L+R): out = False; break
        if out is not None: res.append(out)
    return res
files = sorted(Path(sys.argv[1]).glob('*.csv.gz'))
agg = {k: [] for k in ('15m', '1h', 'daily', 'confluence', '15m_shift', '1h_shift', 'daily_shift')}
prevday = None
for p in files:
    bars = load(p)
    if len(bars) < 380: prevday = None; continue
    p15, p60 = pivots(bars, 15), pivots(bars, 60)
    agg['15m'] += test(bars, p15); agg['15m_shift'] += test(bars, p15, 7.3)
    agg['1h'] += test(bars, p60); agg['1h_shift'] += test(bars, p60, 7.3)
    conf = {hm: (p15[hm]+p60[hm])/2 for hm in p15 if hm in p60 and abs(p15[hm]-p60[hm]) <= 2}
    agg['confluence'] += test(bars, conf)
    if prevday:
        dp = {b[0]: prevday for b in bars}
        agg['daily'] += test(bars, dp); agg['daily_shift'] += test(bars, dp, 7.3)
    prevday = (max(b[1] for b in bars)+min(b[2] for b in bars)+bars[-1][3])/3
for k, v in agg.items():
    print(f'{k:12s} touches {len(v):5d}  bounce {100*sum(v)/len(v):.1f}%' if v else f'{k}: none')
