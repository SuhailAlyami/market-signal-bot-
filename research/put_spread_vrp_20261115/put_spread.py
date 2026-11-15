"""Defined-risk SPX put credit spread on modelled prices (protocol.json). Research only."""
import gzip
import hashlib
import json
import math
import random
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE.parent/'volatility_premium_20261115'
T = 30/365
N = lambda x: 0.5*(1+math.erf(x/math.sqrt(2)))


def bs_put(S, K, sig, t=T):
    if sig <= 0:
        return max(K-S, 0.0)
    d1 = (math.log(S/K)+0.5*sig*sig*t)/(sig*math.sqrt(t))
    return K*N(-(d1-sig*math.sqrt(t)))-S*N(-d1)


def load(name):
    r = json.loads(gzip.open(DATA/f'{name}_1d.json.gz').read())['chart']['result'][0]
    return {datetime.fromtimestamp(t, timezone.utc).date(): c for t, c in zip(r['timestamp'], r['indicators']['quote'][0]['close']) if c}


def cycles(cost=2.0, side=1):
    spx, vix = load('GSPC'), load('VIX')
    days = sorted(set(spx) & set(vix))
    out, i = [], 0
    while i+21 < len(days):
        d0, d1 = days[i], days[i+21]
        S, sig, ST = spx[d0], vix[d0]/100, spx[d1]
        k1 = S*math.exp(-sig*math.sqrt(T))
        k2 = k1-0.5*S*sig*math.sqrt(T)
        credit = bs_put(S, k1, sig)-bs_put(S, k2, sig)
        payout = min(max(k1-ST, 0.0), k1-k2)
        net = side*(credit-payout)-cost
        out.append({'entry': d0.isoformat(), 'expiry': d1.isoformat(), 'S': S, 'vix': vix[d0], 'k1': k1, 'k2': k2,
                    'credit': credit, 'payout': payout, 'net': net, 'max_risk': (k1-k2)-credit, 'spx_change': ST-S})
        i += 21
    return out


def summ(rows):
    net = [r['net'] for r in rows]
    cum = peak = mdd = 0.0
    for v in net:
        cum += v; peak = max(peak, cum); mdd = max(mdd, peak-cum)
    return {'cycles': len(rows), 'win_rate': round(sum(v > 0 for v in net)/len(net), 3), 'mean_net': round(st.mean(net), 2),
            'total_net': round(sum(net), 1), 'worst': round(min(net), 1), 'max_drawdown': round(mdd, 1),
            'mean_pct_of_max_risk': round(100*st.mean(r['net']/r['max_risk'] for r in rows), 2),
            'mean_credit': round(st.mean(r['credit'] for r in rows), 2), 'mean_width': round(st.mean(r['k1']-r['k2'] for r in rows), 1)}


def ci(rows, seed=1601):
    rng = random.Random(seed)
    net = [r['net'] for r in rows]
    b = sorted(st.mean(rng.choices(net, k=len(net))) for _ in range(2000))
    return [round(b[49], 2), round(b[1949], 2)]


BLOCKS = {'A_1990_1999': (1990, 1999), 'B_2000_2009': (2000, 2009), 'C_2010_2022': (2010, 2022), 'D_2023_2026': (2023, 2026)}


def run():
    out = {'protocol_sha256': hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()}
    for cost in (2.0, 4.0):
        sell, buy = cycles(cost, 1), cycles(cost, -1)
        res = {'full_sell': summ(sell), 'full_sell_ci95': ci(sell), 'full_buy': summ(buy),
               'spx_change_mean_points': round(st.mean(r['spx_change'] for r in sell), 1)}
        for name, (a, b) in BLOCKS.items():
            sub = [r for r in sell if a <= int(r['entry'][:4]) <= b]
            res[name] = dict(summ(sub), ci95=ci(sub))
        res['worst_5'] = [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items() if k in ('entry', 'vix', 'net', 'spx_change')}
                          for r in sorted(sell, key=lambda r: r['net'])[:5]]
        out[f'cost_{cost:g}'] = res
    r2 = out['cost_2']
    if r2['full_sell']['mean_net'] <= 0:
        v = 'FAILURE'
    elif all(r2[b]['mean_net'] > 0 for b in BLOCKS) and r2['full_sell_ci95'][0] > 0:
        v = 'SUCCESS'
    else:
        v = 'INCONCLUSIVE'
    out['verdict'] = v
    return out


if __name__ == '__main__':
    json.dump(run(), sys.stdout, indent=1)
