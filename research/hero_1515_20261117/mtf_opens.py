"""'درع الأوبشن - التوقع' reconstructed: the table values equal the OPEN of the current candle on 5m/15m/1h/4h/1D
(gold clip: 5m=15m and 1h=4h exactly when those candles opened together). Test on SPX 1m RTH (Dukascopy, 479 sessions):
each open becomes a level once its candle starts; first later touch (price comes back to it, at least 5 min after the
candle opened). Bounce = price moves R=5 pts away on the original side before 5 pts through, within 30 min.
Baseline: the same open shifted by 7.3 pts. Candles RTH-aligned like TradingView SPX (1h at :30, 4h at 09:30/13:30)."""
import csv, gzip, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); R = 5.0
def load(p):
    out = []
    for r in csv.DictReader(gzip.open(p, 'rt')):
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY); hm = t.hour*60+t.minute
        if 570 <= hm <= 959: out.append((hm, float(r['Open']), float(r['High']), float(r['Low']), float(r['Close'])))
    return out
def opens(bars, size):
    o = {}
    for b in bars:
        if (b[0]-570) % size == 0: o[b[0]] = b[1]
    return o
def test(bars, lv, shift=0.0):
    res = []
    idx = {b[0]: i for i, b in enumerate(bars)}
    for start, price in lv.items():
        L = price+shift; i0 = idx.get(start)
        if i0 is None: continue
        for i in range(i0+5, len(bars)-1):
            if bars[i][0] > 930: break
            pc = bars[i-1][4]; h, l = bars[i][2], bars[i][3]
            if l <= L <= h and abs(pc-L) > 0.25:
                side = 1 if pc > L else -1; out = None
                for b in bars[i+1:i+31]:
                    if (b[2] >= L+R if side > 0 else b[3] <= L-R): out = True; break
                    if (b[3] <= L-R if side > 0 else b[2] >= L+R): out = False; break
                if out is not None: res.append(out)
                break
    return res
agg = {}
for p in sorted(Path(sys.argv[1]).glob('*.csv.gz')):
    bars = load(p)
    if len(bars) < 380: continue
    for name, size in (('5m', 5), ('15m', 15), ('1h', 60), ('4h', 240), ('day', 390)):
        lv = opens(bars, size)
        agg.setdefault(name, []).extend(test(bars, lv)); agg.setdefault(name+'_shifted', []).extend(test(bars, lv, 7.3))
for k in ('5m', '15m', '1h', '4h', 'day'):
    a, b = agg[k], agg[k+'_shifted']
    print(f'{k:4s} open: touches {len(a):5d} bounce {100*sum(a)/len(a):.1f}%   | shifted (random) {len(b):5d} bounce {100*sum(b)/len(b):.1f}%')
