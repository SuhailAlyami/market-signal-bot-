"""'Hero' 15:15 candle breakout on SPX (Dukascopy US500 1m bid, DELAYED_RESEARCH_ONLY). Rules fixed before running:
Reference candle starts 15:15 New York (= 23:15 Riyadh winter / 22:15 summer). Variants: 5-min (15:15-15:20) and 15-min (15:15-15:30).
Levels: 0 = candle low, 1 = candle high, R = high-low, 0.5 = mid. Entry: first 1-min CLOSE after the candle ends that is above
level 1 (CALL) or below level 0 (PUT), up to 15:55; entry price = that close. Stop: mid touched. Targets: CALL low+2R / PUT high-2R
(the slide's level 2 / level -1), also low+3R / high-3R. Exit at the 15:59 close if neither. Same-bar stop+target counts as stop.
Results in SPX points per trade (underlying only, no option prices), by year. Baseline: same entry time, opposite direction,
same mirrored stop/target (if the rule has an edge, the mirror must be clearly worse)."""
import csv, gzip, json, sys, statistics as st
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York')
def session(path):
    rows = []
    for r in csv.DictReader(gzip.open(path, 'rt')):
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY)
        rows.append((t.strftime('%H:%M'), float(r['High']), float(r['Low']), float(r['Close'])))
    return rows
def trade(bars, side, entry, stop, target):
    for hm, h, l, c in bars:
        hit_stop = l <= stop if side > 0 else h >= stop
        hit_tgt = h >= target if side > 0 else l <= target
        if hit_stop: return stop - entry if side > 0 else entry - stop, 'stop'
        if hit_tgt: return target - entry if side > 0 else entry - target, 'target'
    c = bars[-1][3] if bars else entry
    return (c - entry)*side, 'close'
res = {}
for minutes in (5, 15):
    end = {5: '15:20', 15: '15:30'}[minutes]
    for tmult in (2, 3):
        out, mirror = [], []
        for p in sorted(Path(sys.argv[1]).glob('*.csv.gz')):
            bars = session(p)
            ref = [b for b in bars if '15:15' <= b[0] < end]
            after = [b for b in bars if end <= b[0] <= '15:59']
            if len(ref) < minutes - 1 or not after or bars[-1][0] < '15:55':
                continue   # early-close or incomplete session
            H, L = max(b[1] for b in ref), min(b[2] for b in ref); R = H - L; mid = (H+L)/2
            if R <= 0: continue
            for i, (hm, h, l, c) in enumerate(after):
                if hm > '15:55': break
                side = 1 if c > H else (-1 if c < L else 0)
                if side:
                    tgt = L + tmult*R if side > 0 else H - tmult*R
                    pnl, how = trade(after[i+1:], side, c, mid, tgt)
                    mt = c - (tgt - c) if side > 0 else c + (c - tgt)       # mirrored target for opposite side
                    ms = c + (c - mid) if side > 0 else c - (mid - c)      # mirrored stop
                    mp, _ = trade(after[i+1:], -side, c, ms, mt)
                    out.append({'d': p.name[:10], 'side': side, 'pnl': pnl, 'how': how, 'R': R}); mirror.append(mp)
                    break
        def summ(xs):
            g = [x['pnl'] for x in xs]
            if not g: return {'n': 0}
            win = [v for v in g if v > 0]; loss = [-v for v in g if v < 0]
            return {'n': len(g), 'win_pct': round(100*len(win)/len(g), 1), 'mean_pts': round(st.mean(g), 2),
                    'total_pts': round(sum(g), 1), 'profit_factor': round(sum(win)/sum(loss), 2) if loss else None,
                    'target_pct': round(100*sum(x['how'] == 'target' for x in xs)/len(xs), 1)}
        key = f'{minutes}min_target{tmult}R'
        res[key] = {'all': summ(out), '2025': summ([x for x in out if x['d'] < '2026']), '2026': summ([x for x in out if x['d'] >= '2026']),
                    'CALL': summ([x for x in out if x['side'] > 0]), 'PUT': summ([x for x in out if x['side'] < 0]),
                    'mirror_opposite_mean_pts': round(st.mean(mirror), 2) if mirror else None,
                    'median_candle_range_pts': round(st.median(x['R'] for x in out), 1) if out else None}
print(json.dumps({'sessions_dir': sys.argv[1], 'results': res}, indent=1))
