import json, sys, math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); D = sys.argv[1]
r = json.load(open(f'{D}/long_%5EGSPC.json'))['chart']['result'][0]; q = r['indicators']['quote'][0]
c = {datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat(): q['close'][i] for i, t in enumerate(r['timestamp']) if q['close'][i]}
days = sorted(d for d in c if d < '2026-11-28')
ltd = {days[i] for i in range(len(days)-1) if days[i][:7] != days[i+1][:7]}
ftd = {days[i] for i in range(1, len(days)) if days[i][:7] != days[i-1][:7]}
def binom_p(k, n, p):   # two-sided normal approx
    z = (k - n*p)/math.sqrt(n*p*(1-p)); return z, math.erfc(abs(z)/math.sqrt(2))
for lo, hi in (('1990','1999'),('2000','2009'),('2010','2017'),('2018','2026'),('1990','2009'),('2010','2026')):
    sel = [i for i in range(1, len(days)) if lo <= days[i][:4] <= hi]
    up = lambda i: c[days[i]] > c[days[i-1]]
    L = [up(i) for i in sel if days[i] in ltd]; O = [up(i) for i in sel if days[i] not in ltd and days[i] not in ftd]; F = [up(i) for i in sel if days[i] in ftd]
    base = sum(O)/len(O)
    zl, pl = binom_p(sum(L), len(L), base); zf, pf = binom_p(sum(F), len(F), base)
    ret = lambda i: 100*(c[days[i]]/c[days[i-1]]-1)
    ml = sum(ret(i) for i in sel if days[i] in ltd)/len(L)
    print(f'{lo}-{hi}: LTD up {100*sum(L)/len(L):.0f}% n={len(L)} mean {ml:+.3f}% (z {zl:+.1f} p {pl:.3f}) | FTD up {100*sum(F)/len(F):.0f}% (z {zf:+.1f}) | other {100*base:.0f}%')
# last 3 Novembers-ending / Monday LTDs recent
print([ (d, round(100*(c[d]/c[days[days.index(d)-1]]-1),2)) for d in sorted(ltd)[-12:]])
