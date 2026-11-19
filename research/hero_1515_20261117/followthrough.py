"""Intraday follow-through after a strong move is already visible (rules fixed before running).
Data: Dukascopy US500 1m (RTH), 479 sessions 2025-01..2026-11-10; m = prev close * VIX_prev/100/sqrt(252) (daily Yahoo).
Trigger: first 1-min close between 09:45 and 14:30 NY with |close - open| >= k*m (k = 0.5, also 0.35 and 0.75).
Alert latency: 15 minutes (delayed data). Entry = 1-min close 15 min after the trigger, in the move's direction.
Outcome: points from entry to the 15:59 close; also the adverse excursion (worst point against) before the close.
Split by year for stability. Underlying points only, no option prices."""
import csv, gzip, json, math, sys, statistics as st
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York')
def ld(s):
    r = json.loads(gzip.open(Path(sys.argv[2])/f'{s}_1d.json.gz').read())['chart']['result'][0]; q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).date().isoformat(): q['close'][i] for i, t in enumerate(r['timestamp']) if q['close'][i]}
vix, spxd = ld('VIX'), ld('GSPC'); dd = sorted(spxd)
res = {}
for k in (0.35, 0.5, 0.75):
    out = []
    for p in sorted(Path(sys.argv[1]).glob('*.csv.gz')):
        day = p.name[:10]
        prev = [d for d in dd if d < day]
        if not prev or prev[-1] not in vix: continue
        pc = spxd[prev[-1]]; m = pc*vix[prev[-1]]/100/math.sqrt(252)
        bars = []
        for r in csv.DictReader(gzip.open(p, 'rt')):
            t = datetime.fromisoformat(r['timestamp']).astimezone(NY).strftime('%H:%M')
            if '09:30' <= t <= '15:59': bars.append((t, float(r['High']), float(r['Low']), float(r['Close'])))
        if len(bars) < 380: continue
        o = bars[0][3]; close = bars[-1][3]
        for i, (t, h, l, c) in enumerate(bars):
            if not ('09:45' <= t <= '14:30'): continue
            if abs(c-o) >= k*m:
                side = 1 if c > o else -1
                j = min(i+15, len(bars)-1); e = bars[j][3]
                rest = bars[j+1:]
                adverse = max(((e - b[2]) if side > 0 else (b[1] - e)) for b in rest) if rest else 0
                out.append({'d': day, 't': t, 'pnl': (close-e)*side, 'adv': adverse, 'm': m, 'move_at_trigger': abs(c-o)})
                break
    def summ(xs):
        g = [x['pnl'] for x in xs]
        if not g: return {'n': 0}
        return {'n': len(g), 'win%': round(100*sum(v > 0 for v in g)/len(g)), 'mean_pts': round(st.mean(g), 1), 'median_pts': round(st.median(g), 1),
                'total_pts': round(sum(g)), 'mean_adverse_pts': round(st.mean(x['adv'] for x in xs), 1),
                'pf': round(sum(v for v in g if v > 0)/max(1e-9, -sum(v for v in g if v < 0)), 2)}
    res[f'k={k}'] = {'all': summ(out), '2025': summ([x for x in out if x['d'] < '2026']), '2026': summ([x for x in out if x['d'] >= '2026'])}
print(json.dumps(res, indent=1))
