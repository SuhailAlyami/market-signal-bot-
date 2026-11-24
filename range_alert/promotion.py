"""Automatic proof gate: every candidate signal is scored on LIVE sessions only (after the research data ended on
2026-11-13), using SPY open/close as the tradable price. The daily message reads the status, with no human step:
  PROVEN  -> shown as a direct recommendation
  TESTING -> shown as a conditional plan with its live record
  FAILED  -> removed from the message automatically
The thresholds below are fixed in advance and must not be tuned on live results (that would be in-sample again).
"""
import math
import statistics as st

LIVE_START = '2026-11-16'     # first session after the research history (last research day 2026-11-13)
TRADE_K = 0.5                 # gap threshold in expected moves (chosen on 2010-2019, research/gap_trade_20261124)
DIR_K = 0.2                   # gap threshold for the open-to-close direction call
COST_PT = 1.0                 # round-trip cost in SPX points (0.10 SPY $)
MIN_TRADES = 30
MIN_DIR = 40
CLAIMS = {'high': 72, 'low': 69, 'range': 69}   # promised hit rates printed in the morning message


def wilson(k, n, z=1.96):
    if n == 0:
        return 0.0, 1.0
    p = k/n
    d = 1+z*z/n
    c = (p+z*z/(2*n))/d
    h = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return c-h, c+h


def mean_ci(x, z=1.96):
    if len(x) < 2:
        return (float('-inf'), float('inf'))
    m, se = st.mean(x), st.stdev(x)/math.sqrt(len(x))
    return m-z*se, m+z*se


def live_rows(spx, vix, spy, start=LIVE_START):
    """One row per live session with everything known before the open (pc, m, gap) and the outcome."""
    days = sorted(d for d in spx if d in spy)
    out = []
    for p, d in zip(days, days[1:]):
        if d < start or p not in vix:
            continue
        pc, so = spx[p][3], spx[d][0]
        m = pc*vix[p][3]/100/math.sqrt(252)
        if m <= 0:
            continue
        out.append({'d': d, 'pc': pc, 'm': m, 'g': (so-pc)/m, 'spx': spx[d], 'spy_o': spy[d][0], 'spy_c': spy[d][3]})
    return out


def trade_record(rows, k=TRADE_K):
    """Conditional gap trade on SPX levels, P&L from SPY open->close in SPX points (x10), after cost."""
    pnl = []
    for r in rows:
        if abs(r['g']) < k:
            continue
        side = 1 if r['g'] > 0 else -1
        pnl.append(10*side*(r['spy_c']-r['spy_o'])-COST_PT)
    n, w = len(pnl), sum(x > 0 for x in pnl)
    lo, hi = mean_ci(pnl)
    wlo, _ = wilson(w, n)
    if n >= MIN_TRADES and lo > 0 and wlo > 0.5:
        status = 'PROVEN'
    elif n >= MIN_TRADES and hi < 0:
        status = 'FAILED'
    else:
        status = 'TESTING'
    return {'status': status, 'n': n, 'wins': w, 'avg': round(st.mean(pnl), 1) if pnl else None,
            'total': round(sum(pnl)) if pnl else 0, 'ci': (round(lo, 1), round(hi, 1)) if n >= 2 else None}


def direction_record(rows, k=DIR_K):
    hits = [(r['spy_c'] > r['spy_o']) == (r['g'] > 0) for r in rows if abs(r['g']) >= k and r['spy_c'] != r['spy_o']]
    n, w = len(hits), sum(hits)
    lo, hi = wilson(w, n)
    status = 'PROVEN' if n >= MIN_DIR and lo > 0.5 else ('FAILED' if n >= MIN_DIR and hi < 0.55 else 'TESTING')
    return {'status': status, 'n': n, 'hits': w}


def level_record(rows, k_high, k_low):
    """Live hit rates of the printed levels vs the promised ones. OFF when the promise is outside the 95% interval."""
    res = {}
    for key, test in (('high', lambda r: r['spx'][1] >= r['pc']+k_high*r['m']),
                      ('low', lambda r: r['spx'][2] <= r['pc']-k_low*r['m']),
                      ('range', lambda r: r['pc']-r['m'] <= r['spx'][2] and r['spx'][1] <= r['pc']+r['m'])):
        n, w = len(rows), sum(map(test, rows))
        lo, hi = wilson(w, n)
        res[key] = {'n': n, 'hits': w, 'claim': CLAIMS[key], 'ok': n < 20 or lo*100 <= CLAIMS[key] <= hi*100}
    return res


def reversal_record(spx, spy, start=LIVE_START):
    """After the 3rd straight lower SPX close, buy at that close and exit at the next close (SPY prices, x10, after
    cost). Found post hoc in research/boom_20261124/close_reversal.py (it was NOT the preselected rule), so it can
    only be judged on live sessions."""
    days = sorted(d for d in spx if d in spy)
    pnl = []
    for i in range(3, len(days)-1):
        d = days[i]
        if d < start:
            continue
        if all(spx[days[i-k]][3] < spx[days[i-k-1]][3] for k in range(3)):
            pnl.append(10*(spy[days[i+1]][3]-spy[d][3])-COST_PT)
    n, w = len(pnl), sum(x > 0 for x in pnl)
    lo, hi = mean_ci(pnl)
    status = ('PROVEN' if n >= MIN_TRADES and lo > 0 and wilson(w, n)[0] > 0.5 else
              'FAILED' if n >= MIN_TRADES and hi < 0 else 'TESTING')
    return {'status': status, 'n': n, 'wins': w, 'total': round(sum(pnl)) if pnl else 0}


def evaluate(spx, vix, spy, k_high, k_low):
    rows = live_rows(spx, vix, spy)
    return {'since': LIVE_START, 'sessions': len(rows), 'trade': trade_record(rows),
            'direction': direction_record(rows), 'levels': level_record(rows, k_high, k_low),
            'reversal': reversal_record(spx, spy)}


def fetch(k_high, k_low):
    """Network version used by the morning and evening jobs (Yahoo daily, completed sessions only)."""
    import explosion as X
    return evaluate(X.yahoo_daily('^GSPC', '2026-10-20'), X.yahoo_daily('^VIX', '2026-10-20'),
                    X.yahoo_daily('SPY', '2026-10-20'), k_high, k_low)


def record_line(g):
    t, d, lv = g['trade'], g['direction'], g['levels']
    tr = (f"الصفقة {t['wins']}/{t['n']} رابحة، {t['total']:+,} نقطة" if t['n'] else "الصفقة لم تتفعّل بعد")
    rv = g.get('reversal')
    if rv and rv['n']:
        tr += f" | الارتداد {rv['wins']}/{rv['n']}، {rv['total']:+,} نقطة"
    lvl = ' | '.join(f"{name} {lv[k]['hits']}/{lv[k]['n']} (المعلن {lv[k]['claim']}%){'' if lv[k]['ok'] else ' ⚠️'}"
                     for k, name in (('high', 'القمة'), ('low', 'القاع'), ('range', 'المدى')))
    return (f"📒 السجل الحي منذ {g['since']} ({g['sessions']} جلسة، أسعار SPY): {tr} | "
            f"الاتجاه من الافتتاح {d['hits']}/{d['n']} | {lvl}")
