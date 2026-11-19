"""Gamma radar: dealer gamma positioning for SPX from CBOE's free delayed option chain (DELAYED_RESEARCH_ONLY).
Convention (an assumption, not observed positioning): dealers are long customer-sold calls and short customer-bought
puts, so call gamma counts +, put gamma counts -. Dollar gamma per 1% move = gamma * OI * 100 * S^2 * 0.01.
Outputs: net gamma (all expiries, <=1 day, <=7 days), the flip level where the net-gamma profile changes sign
(Black-Scholes gamma recomputed at hypothetical spots with each option's IV), and call/put walls.
Research only: no alert is driven by it until a forward record shows it separates explosion days."""
import json
import math
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
URL = 'https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json'
SYM = re.compile(r'^(SPXW?)(\d{6})([CP])(\d{8})$')


def fetch(tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; suhail-hunter-gamma-radar)'})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:  # noqa: BLE001
            last = e
            import time; time.sleep(10*(i+1))
    raise RuntimeError(f'CBOE unavailable: {last}')


def parse(opt):
    m = SYM.match(opt['option'])
    if not m:
        return None
    root, ymd, cp, k = m.groups()
    exp = datetime(2000+int(ymd[:2]), int(ymd[2:4]), int(ymd[4:]), 16, 0, tzinfo=NY)   # PM-settled close (AM roots ignored below)
    return {'root': root, 'exp': exp, 'cp': cp, 'k': int(k)/1000, 'oi': opt.get('open_interest') or 0,
            'iv': opt.get('iv') or 0, 'gamma': opt.get('gamma') or 0}


def bs_gamma(s, k, t, iv):
    if t <= 0 or iv <= 0:
        return 0.0
    d1 = (math.log(s/k) + 0.5*iv*iv*t)/(iv*math.sqrt(t))
    return math.exp(-0.5*d1*d1)/math.sqrt(2*math.pi)/(s*iv*math.sqrt(t))


def analyse(chain, now=None):
    d = chain['data']
    spot = float(d['current_price'])
    now = now or datetime.now(timezone.utc)
    opts = [o for o in (parse(x) for x in d['options']) if o and o['oi'] > 0 and o['exp'] > now and abs(o['k']/spot-1) < 0.3]
    dollar = lambda g, oi: g*oi*100*spot*spot*0.01
    sign = lambda o: 1 if o['cp'] == 'C' else -1
    def net(maxdays):
        lim = now + timedelta(days=maxdays)
        return sum(sign(o)*dollar(o['gamma'], o['oi']) for o in opts if o['exp'] <= lim)/1e9
    # profile: recompute gamma at hypothetical spots (IV and time to expiry held fixed)
    grid = [spot*(1+x/400) for x in range(-40, 41)]                  # +/-10% in 0.25% steps
    prof = []
    for s in grid:
        tot = 0.0
        for o in opts:
            t = (o['exp']-now).total_seconds()/(365*24*3600)
            tot += sign(o)*bs_gamma(s, o['k'], t, o['iv'])*o['oi']*100*s*s*0.01
        prof.append(tot/1e9)
    flips = [grid[i] + (grid[i+1]-grid[i])*prof[i]/(prof[i]-prof[i+1]) for i in range(len(grid)-1) if prof[i]*prof[i+1] < 0]
    flip = min(flips, key=lambda f: abs(f-spot)) if flips else None
    by_k = {}
    for o in opts:
        if o['exp'] <= now + timedelta(days=30):
            by_k.setdefault(o['k'], [0.0, 0.0])[0 if o['cp'] == 'C' else 1] += dollar(o['gamma'], o['oi'])
    calls = [(k, v[0]) for k, v in by_k.items() if k >= spot]
    puts = [(k, v[1]) for k, v in by_k.items() if k <= spot]
    g_all = net(3650)
    return {'cboe_timestamp': chain.get('timestamp'), 'spot': round(spot, 2), 'prev_close': d.get('prev_day_close'),
            'last_trade_time': d.get('last_trade_time'), 'n_options': len(opts),
            'net_gamma_bn_per_1pct': round(g_all, 2), 'net_gamma_le1d': round(net(1.2), 2), 'net_gamma_le7d': round(net(7.2), 2),
            'flip': round(flip, 1) if flip else None,
            'regime': 'negative' if (flip and spot < flip) or (not flip and g_all < 0) else 'positive',
            'call_wall': max(calls, key=lambda x: x[1])[0] if calls else None,
            'put_wall': max(puts, key=lambda x: x[1])[0] if puts else None,
            'convention': 'dealers long calls / short puts (assumed)', 'classification': 'DELAYED_RESEARCH_ONLY'}


if __name__ == '__main__':
    out = analyse(fetch())
    day = datetime.now(NY).date().isoformat()
    out['collected_ny'] = datetime.now(NY).isoformat(timespec='minutes')
    print('GAMMA_JSON ' + json.dumps(out))
    if len(sys.argv) > 1:
        open(sys.argv[1], 'w').write(json.dumps(out, indent=1)+'\n')
