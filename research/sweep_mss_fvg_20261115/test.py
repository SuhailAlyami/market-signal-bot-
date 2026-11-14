"""Video 3 (@qimainvestclub): prev-day H/L liquidity sweep -> 5m MSS -> FVG entry, stop beyond sweep, target opposite prev-day extreme.
Rules frozen before running. Research only.
 sweep  : bar high > prevH (bear) / low < prevL (bull), bar index >=1
 MSS    : later close below min low (bear) / above max high (bull) of the 5 bars before the sweep bar, within 12 bars of sweep
 FVG    : most recent 3-bar gap between sweep bar and MSS bar: bear bar[k-2].low > bar[k].high ; bull bar[k-2].high < bar[k].low
 entry  : limit at the near edge of the FVG (bear: bar[k].high ; bull: bar[k].low) on a bar after MSS, before 15:30 NY
          variant B: no FVG required, enter at MSS bar close
 stop   : sweep extreme +/-0.02% ; target: prevL (bear) / prevH (bull) ; else exit at session close
 same-bar entry+stop or stop+target -> stop. cost 0.03% RT. Baseline: random direction, same distances."""
import sys, json, random
sys.path.insert(0, 'research/ict_daily_sweep_20261114')
from test import yahoo_sessions, repo5m_sessions, git, stats
COST = 0.03

def sim(cb, e_idx, ep, side, tgt, stp, check_entry_bar):
    risk = abs(ep - stp) / ep * 100
    if risk <= 0: return None
    def out(dd, tg, sp):
        bars = cb[e_idx:] if check_entry_bar else cb[e_idx+1:]
        for b in bars:
            if (dd == -1 and b['h'] >= sp) or (dd == 1 and b['l'] <= sp): return sp, 'stop'
            if (dd == -1 and b['l'] <= tg) or (dd == 1 and b['h'] >= tg): return tg, 'target'
        return cb[-1]['c'], 'eod'
    x, why = out(side, tgt, stp)
    net = (x - ep) / ep * 100 * side - COST
    td, sd = abs(tgt - ep), abs(ep - stp); bl = []
    for dd in (1, -1):
        x2, _ = out(dd, ep + dd * td, ep - dd * sd); bl.append(((x2 - ep) / ep * 100 * dd - COST) / risk)
    return {'net': net, 'R': net / risk, 'exit': why, 'base_R': sum(bl) / 2}

def run(sess, variant, mb, last_entry='15:30'):
    days = list(sess); tr = []
    for i in range(1, len(days)):
        pb, cb = sess[days[i-1]], sess[days[i]]
        if len(pb) < mb or len(cb) < mb: continue
        pH = max(b['h'] for b in pb); pL = min(b['l'] for b in pb)
        for side in (-1, 1):                      # -1 = bear (sweep high), 1 = bull (sweep low)
            s = next((j for j in range(1, len(cb)) if (cb[j]['h'] > pH if side == -1 else cb[j]['l'] < pL)), None)
            if s is None or s < 1: continue
            ref = cb[max(0, s-5):s]
            lvl = min(b['l'] for b in ref) if side == -1 else max(b['h'] for b in ref)
            m = next((j for j in range(s+1, min(len(cb), s+13)) if (cb[j]['c'] < lvl if side == -1 else cb[j]['c'] > lvl)), None)
            if m is None: continue
            ext = max(b['h'] for b in cb[s:m+1]) if side == -1 else min(b['l'] for b in cb[s:m+1])
            stp = ext * (1.0002 if side == -1 else 0.9998); tgt = pL if side == -1 else pH
            if variant == 'B':
                ep = cb[m]['c']
                if (side == -1 and ep <= tgt) or (side == 1 and ep >= tgt): continue
                r = sim(cb, m, ep, side, tgt, stp, False)
            else:
                fvg = None
                for k in range(max(s, 2), m+1):
                    if side == -1 and cb[k-2]['l'] > cb[k]['h']: fvg = cb[k]['h']
                    if side == 1 and cb[k-2]['h'] < cb[k]['l']: fvg = cb[k]['l']
                if fvg is None: continue
                if (side == -1 and (fvg <= tgt or fvg >= stp)) or (side == 1 and (fvg >= tgt or fvg <= stp)): continue
                e = next((j for j in range(m+1, len(cb)) if cb[j]['t'] < last_entry and
                          ((side == -1 and cb[j]['h'] >= fvg) or (side == 1 and cb[j]['l'] <= fvg))), None)
                if e is None: continue
                # if target reached between MSS and fill, setup is void (price already left)
                if any((side == -1 and b['l'] <= tgt) or (side == 1 and b['h'] >= tgt) for b in cb[m+1:e]): continue
                r = sim(cb, e, fvg, side, tgt, stp, True)
            if r: r.update({'day': days[i], 'dir': 'S' if side == -1 else 'L'}); tr.append(r)
    return tr

if __name__ == '__main__':
    H = 'origin/data-history-20261114'; out = {}
    layers = [('SPX_5m_64', repo5m_sessions(), 20, 'data/spx-collection:breadth5m/bars5m.json'),
              ('SPX_15m_60', yahoo_sessions(git(H, 'history/GSPC_15m_60d.json.gz')), 20, f'{H}:history/GSPC_15m_60d.json.gz'),
              ('SPX_1h_728_proxy', yahoo_sessions(git(H, 'history/GSPC_1h_730d.json.gz')), 5, f'{H}:history/GSPC_1h_730d.json.gz'),
              ('SPY_1h_728_proxy', yahoo_sessions(git(H, 'history/SPY_1h_730d.json.gz')), 5, f'{H}:history/SPY_1h_730d.json.gz')]
    for name, sess, mb, src in layers:
        for v in ('A_fvg', 'B_mss_close'):
            tr = run(sess, v[0], mb)
            row = {'source': src, 'sessions': len(sess), 'all': stats(tr)}
            if '1h' in name: row['unseen_before_2026-08-17'] = stats([t for t in tr if t['day'] < '2026-08-17'])
            out[f'{name}|{v}'] = row
            print(f"{name}|{v}: {row['all']}" + (f"\n   unseen: {row['unseen_before_2026-08-17']}" if '1h' in name else ''))
    json.dump(out, open('research/sweep_mss_fvg_20261115/result.json', 'w'), indent=1)
