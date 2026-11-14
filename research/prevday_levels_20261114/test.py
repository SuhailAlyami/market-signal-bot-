"""Do intraday SPX prices react at previous-day RTH levels (H, L, O, C) more than at placebo levels? Research only.
Frozen rules: touch = first bar (from bar 1) whose range contains the level while the previous close was on one side.
Trade: fade at the level (bounce direction), stop and target both d% away (1:1), max K bars, else exit at close of bar K.
Cost 0.03% round trip. R = net%/d. Placebo: same level shifted by a random +/-0.2..1.0% (200 draws per session, seed 7)."""
import sys, json, random
sys.path.insert(0, 'research/ict_daily_sweep_20261114')
from test import yahoo_sessions, repo5m_sessions, git
COST = 0.03

def touches(cb, lvl, d, K):
    out = []
    for j in range(1, len(cb)):
        pc = cb[j-1]['c']; b = cb[j]
        if not (b['l'] <= lvl <= b['h']) or pc == lvl: continue
        side = 1 if pc > lvl else -1                 # approaching from above -> expect bounce up
        tgt = lvl * (1 + side * d / 100); stp = lvl * (1 - side * d / 100); x = None
        # entry at level; the touch bar itself may already hit stop -> conservative
        if (side == 1 and b['l'] <= stp) or (side == -1 and b['h'] >= stp): x = stp
        else:
            for k in cb[j+1:j+1+K]:
                if (side == 1 and k['l'] <= stp) or (side == -1 and k['h'] >= stp): x = stp; break
                if (side == 1 and k['h'] >= tgt) or (side == -1 and k['l'] <= tgt): x = tgt; break
            if x is None: x = cb[min(j+K, len(cb)-1)]['c']
        net = (x - lvl) / lvl * 100 * side - COST
        out.append(net / d); break                   # first touch per level per session only
    return out

def run(sess, d, K, mb):
    days = list(sess); real = []; plac = []; rnd = random.Random(7)
    for i in range(1, len(days)):
        pb, cb = sess[days[i-1]], sess[days[i]]
        if len(pb) < mb or len(cb) < mb: continue
        L = {'H': max(b['h'] for b in pb), 'L': min(b['l'] for b in pb), 'O': pb[0]['o'], 'C': pb[-1]['c']}
        for name, lv in L.items():
            for r in touches(cb, lv, d, K): real.append((days[i], name, r))
        for _ in range(200):
            lv = list(L.values())[rnd.randrange(4)] * (1 + rnd.choice((-1, 1)) * rnd.uniform(0.2, 1.0) / 100)
            plac += touches(cb, lv, d, K)
    return real, plac

def ci(v, seed=42):
    r = random.Random(seed); n = len(v); s = sorted(sum(r.choices(v, k=n)) / n for _ in range(3000)); return [round(s[75], 3), round(s[2924], 3)]

if __name__ == '__main__':
    H = 'origin/data-history-20261114'; res = {}
    layers = [('SPX_5m_64', repo5m_sessions(), 0.15, 6, 20, 'data/spx-collection:breadth5m/bars5m.json'),
              ('SPX_1h_728', yahoo_sessions(git(H, 'history/GSPC_1h_730d.json.gz')), 0.30, 2, 5, f'{H}:history/GSPC_1h_730d.json.gz'),
              ('SPY_1h_728', yahoo_sessions(git(H, 'history/SPY_1h_730d.json.gz')), 0.30, 2, 5, f'{H}:history/SPY_1h_730d.json.gz')]
    for name, sess, d, K, mb, src in layers:
        real, plac = run(sess, d, K, mb)
        R = [x[2] for x in real]; mp = sum(plac) / len(plac)
        row = {'source': src, 'sessions': len(sess), 'd%': d, 'K_bars': K, 'n_real': len(R), 'meanR_real': round(sum(R)/len(R), 3),
               'ci_real': ci(R), 'win%_real': round(100*sum(r > 0 for r in R)/len(R), 1), 'n_placebo': len(plac),
               'meanR_placebo': round(mp, 3), 'win%_placebo': round(100*sum(r > 0 for r in plac)/len(plac), 1),
               'edge_vs_placebo': round(sum(R)/len(R) - mp, 3), 'ci_edge': [round(c - mp, 3) for c in ci(R)]}
        if '1h' in name:
            u = [x[2] for x in real if x[0] < '2026-08-17']; row['unseen_n'] = len(u); row['unseen_meanR'] = round(sum(u)/len(u), 3); row['unseen_ci'] = ci(u)
        per = {}
        for lv in 'HLOC':
            v = [x[2] for x in real if x[1] == lv]
            if v: per[lv] = {'n': len(v), 'meanR': round(sum(v)/len(v), 3), 'ci': ci(v)}
        row['per_level'] = per; res[name] = row
        print(name, json.dumps(row, ensure_ascii=False))
    json.dump(res, open('research/prevday_levels_20261114/result.json', 'w'), indent=1)
