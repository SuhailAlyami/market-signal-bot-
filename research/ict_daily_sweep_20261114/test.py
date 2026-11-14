"""ICT daily-range sweep + 50% reclaim setup (from user-supplied TikTok video). Research only.
Rules FROZEN before running on any new data (identical to the 2026-11-14 5m run):
  daily candle = RTH OHLC of previous session derived from intraday bars
  V1 (video-literal): prev day green AND range>=0.5%; long only: sweep below prev_low, then first bar CLOSING above prev_50 -> enter at that close
  V2 (both sides):    prev range>=0.3%; long as V1; short mirror (sweep above prev_high, close below prev_50)
  sweep bar itself cannot be the entry bar; target = opposite prev extreme; stop = swept extreme -/+0.05%; else exit at session close
  same-bar stop & target -> stop (conservative). cost 0.03% round trip. R = net% / risk%.
Baseline: same entry bar, same target/stop distances, random direction (500 draws/trade, seed 7)."""
import json, gzip, subprocess, random, sys, datetime as dt
from zoneinfo import ZoneInfo
from collections import defaultdict
NY = ZoneInfo('America/New_York'); COST = 0.03

def git(ref, path):
    b = subprocess.run(['git', 'show', f'{ref}:{path}'], capture_output=True, check=True).stdout
    return gzip.decompress(b) if path.endswith('.gz') else b

def yahoo_sessions(raw):
    r = json.loads(raw)['chart']['result'][0]; q = r['indicators']['quote'][0]; out = defaultdict(list)
    for i, t in enumerate(r['timestamp']):
        o, h, l, c = q['open'][i], q['high'][i], q['low'][i], q['close'][i]
        if None in (o, h, l, c): continue
        x = dt.datetime.fromtimestamp(t, NY)
        if not (dt.time(9, 30) <= x.time() < dt.time(16, 0)): continue
        out[x.date().isoformat()].append({'t': x.strftime('%H:%M'), 'o': o, 'h': h, 'l': l, 'c': c})
    return dict(sorted(out.items()))

def repo5m_sessions():
    d = json.loads(git('origin/data-spx-collection', 'breadth5m/bars5m.json'))['^GSPC']; out = {}
    for day in sorted(d):
        rows = []
        for line in d[day]['csv'].strip().split('\n')[1:]:
            p = line.split(',')
            try: rows.append({'t': p[0], 'o': float(p[1]), 'h': float(p[2]), 'l': float(p[3]), 'c': float(p[4])})
            except: pass
        out[day] = rows
    return out

def resample(sess, k):
    return {d: [{'t': b[i]['t'], 'o': b[i]['o'], 'h': max(x['h'] for x in b[i:i+k]), 'l': min(x['l'] for x in b[i:i+k]),
                 'c': b[min(i+k, len(b))-1]['c']} for i in range(0, len(b), k)] for d, b in sess.items()}

def run(sess, variant, min_bars):
    days = list(sess); trades = []; eligible = 0
    for i in range(1, len(days)):
        pb, cb = sess[days[i-1]], sess[days[i]]
        if len(pb) < min_bars or len(cb) < min_bars: continue
        eligible += 1
        po, pc = pb[0]['o'], pb[-1]['c']; ph = max(b['h'] for b in pb); pl = min(b['l'] for b in pb)
        rng = (ph - pl) / pc * 100; mid = (ph + pl) / 2
        sides = []
        if variant == 'V1':
            if pc > po and rng >= 0.5: sides = [1]
        else:
            if rng >= 0.3: sides = [1, -1]
        for d in sides:
            lvl, tgt, stp = (pl, ph, pl * 0.9995) if d == 1 else (ph, pl, ph * 1.0005)
            swept = False; e = None
            for j, b in enumerate(cb[:-1]):
                if not swept:
                    swept = b['l'] <= lvl if d == 1 else b['h'] >= lvl
                elif (d == 1 and b['c'] > mid) or (d == -1 and b['c'] < mid):
                    e = j; break
            if e is None: continue
            ep = cb[e]['c']; risk = abs(ep - stp) / ep * 100
            if risk <= 0: continue
            path = cb[e+1:]
            def outcome(dd, tg, sp):
                for b in path:
                    hit_s = b['l'] <= sp if dd == 1 else b['h'] >= sp
                    hit_t = b['h'] >= tg if dd == 1 else b['l'] <= tg
                    if hit_s: return sp, 'stop'
                    if hit_t: return tg, 'target'
                return cb[-1]['c'], 'eod'
            xp, why = outcome(d, tgt, stp)
            net = (xp - ep) / ep * 100 * d - COST
            # baseline: random direction, same distances
            td, sd = abs(tgt - ep), abs(ep - stp); bl = []
            for dd in (1, -1):
                x2, _ = outcome(dd, ep + dd * td, ep - dd * sd)
                bl.append(((x2 - ep) / ep * 100 * dd - COST) / risk)
            trades.append({'day': days[i], 'dir': 'L' if d == 1 else 'S', 'bar': cb[e]['t'], 'net': net, 'R': net / risk,
                           'exit': why, 'base_R': sum(bl) / 2})
    return eligible, trades

def stats(tr, seed=42):
    n = len(tr)
    if n == 0: return {'n': 0}
    random.seed(seed); R = [t['R'] for t in tr]; B = [t['base_R'] for t in tr]; diff = [a - b for a, b in zip(R, B)]
    def ci(v): s = sorted(sum(random.choices(v, k=n)) / n for _ in range(3000)); return [round(s[75], 3), round(s[2924], 3)]
    eq = pk = dd = 0
    for r in R: eq += r; pk = max(pk, eq); dd = min(dd, eq - pk)
    return {'n': n, 'win%': round(100 * sum(r > 0 for r in R) / n, 1), 'meanR': round(sum(R) / n, 3), 'ci_R': ci(R),
            'mean_net%': round(sum(t['net'] for t in tr) / n, 4), 'totalR': round(sum(R), 2), 'maxDD_R': round(dd, 2),
            'baseR': round(sum(B) / n, 3), 'edge_vs_base': round(sum(diff) / n, 3), 'ci_edge': ci(diff),
            'sdR': round((sum((r - sum(R)/n) ** 2 for r in R) / max(n - 1, 1)) ** 0.5, 3),
            'exits': {k: sum(t['exit'] == k for t in tr) for k in ('target', 'stop', 'eod')}}

if __name__ == '__main__':
    H = 'origin/data-history-20261114'
    layers = {
        'SPX_15m_repo(5m->15m)': (resample(repo5m_sessions(), 3), 20, 'origin/data-spx-collection:breadth5m/bars5m.json (Yahoo ^GSPC 5m resampled x3)'),
        'SPX_15m_yahoo60d': (yahoo_sessions(git(H, 'history/GSPC_15m_60d.json.gz')), 20, f'{H}:history/GSPC_15m_60d.json.gz'),
        'SPX_1h_730d': (yahoo_sessions(git(H, 'history/GSPC_1h_730d.json.gz')), 5, f'{H}:history/GSPC_1h_730d.json.gz'),
        'SPY_1h_730d': (yahoo_sessions(git(H, 'history/SPY_1h_730d.json.gz')), 5, f'{H}:history/SPY_1h_730d.json.gz'),
    }
    CUT = '2026-08-17'  # first day of the 64 sessions already used for the 5m run
    out = {}
    for name, (sess, mb, src) in layers.items():
        for v in ('V1', 'V2'):
            el, tr = run(sess, v, mb)
            res = {'source': src, 'sessions': len(sess), 'first': min(sess), 'last': max(sess), 'eligible_pairs': el, 'all': stats(tr)}
            if '1h' in name:
                res['unseen_before_' + CUT] = stats([t for t in tr if t['day'] < CUT])
                res['overlap_from_' + CUT] = stats([t for t in tr if t['day'] >= CUT])
                by = defaultdict(list)
                for t in tr: by[t['day'][:4]].append(t)
                res['by_year'] = {y: stats(v_) for y, v_ in sorted(by.items())}
            out[f'{name}|{v}'] = res
    json.dump(out, open(sys.argv[1] if len(sys.argv) > 1 else 'result.json', 'w'), indent=1)
    for k, r in out.items():
        a = r['all']; print(f"\n{k}  sessions={r['sessions']} {r['first']}..{r['last']}")
        print(f"  ALL: {a}")
        for kk in r:
            if kk.startswith(('unseen', 'overlap')): print(f"  {kk}: {r[kk]}")
        if 'by_year' in r:
            for y, s in r['by_year'].items(): print(f"   {y}: n={s['n']} meanR={s.get('meanR')} ci={s.get('ci_R')} win%={s.get('win%')}")
