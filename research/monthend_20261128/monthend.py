"""Pre-registered month-end tests. Discovery 1990-2009, untouched test 2010-2026.
H1 last trading day (LTD) open->close up-rate vs other days. H2 LTD explosion rate |C-O|>=0.75m vs other days.
H3 rebalancing: on LTD, sign(C-O) opposite to month-to-date return (prior close vs prior month's last close), all and |MTD|>=3%.
H4 first trading day of month (FTD) close-to-close up-rate. H5 LTD close vs prev close up-rate."""
import json, math, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); D = sys.argv[1]
def load(s):
    r = json.load(open(f'{D}/long_{s}.json'))['chart']['result'][0]; q = r['indicators']['quote'][0]
    return {datetime.fromtimestamp(t, timezone.utc).astimezone(NY).date().isoformat(): (q['open'][i], q['high'][i], q['low'][i], q['close'][i])
            for i, t in enumerate(r['timestamp']) if None not in (q['open'][i], q['close'][i])}
spx = load('%5EGSPC'); vix = {d: v[3] for d, v in load('%5EVIX').items()}
days = sorted(d for d in spx if d < '2026-11-28'); print('days', days[0], days[-1], len(days))
ltd = {days[i] for i in range(len(days)-1) if days[i][:7] != days[i+1][:7]}
ftd = {days[i] for i in range(1, len(days)) if days[i][:7] != days[i-1][:7]}
def stats(period):
    lo, hi = period
    R = {'ltd': [], 'oth': [], 'ftd': []}
    for i in range(1, len(days)):
        d = days[i]
        if not (lo <= d[:4] <= hi): continue
        o, h, l, c = spx[d]; pc = spx[days[i-1]][3]; v = vix.get(days[i-1])
        if v is None or abs(o-pc) < 1e-6: continue
        m = pc*v/100/math.sqrt(252)
        # month-to-date at prior close: from last close of the previous month
        j = i-1
        while j > 0 and days[j][:7] == d[:7]: j -= 1
        mtd = spx[days[i-1]][3]/spx[days[j]][3]-1 if days[j][:7] != d[:7] else 0
        rec = dict(up_oc=c > o, up_cc=c > pc, boom=abs(c-o) >= .75*m, oc=(c-o)/m, mtd=mtd, gap=(o-pc)/m)
        R['ltd' if d in ltd else 'oth'].append(rec)
        if d in ftd: R['ftd'].append(rec)
    p = lambda xs, k: f"{100*sum(x[k] for x in xs)/max(1,len(xs)):.0f}% (n={len(xs)})"
    L, O, F = R['ltd'], R['oth'], R['ftd']
    print(f'== {lo}-{hi}')
    print(' H1 open->close up: LTD', p(L, 'up_oc'), '| other', p(O, 'up_oc'))
    print(' H2 explosion:      LTD', p(L, 'boom'), '| other', p(O, 'boom'))
    print(' H5 close>prevclose LTD', p(L, 'up_cc'), '| other', p(O, 'up_cc'))
    print(' H4 FTD close>prev ', p(F, 'up_cc'))
    for thr in (0, .03):
        xs = [x for x in L if abs(x['mtd']) >= thr and x['mtd'] != 0]
        opp = sum((x['oc'] > 0) != (x['mtd'] > 0) for x in xs)
        print(f' H3 LTD C-O opposite to MTD (|MTD|>={thr:.0%}): {opp}/{len(xs)} = {100*opp/max(1,len(xs)):.0f}%')
    # gap direction on LTD vs other days (current morning rule)
    for name, xs in (('LTD', L), ('other', O)):
        g = [x for x in xs if abs(x['gap']) >= .2]
        ok = sum((x['gap'] > 0) == x['up_cc'] for x in g)
        print(f' gap rule (|gap|>=0.2m) {name}: {ok}/{len(g)} = {100*ok/max(1,len(g)):.0f}%')
stats(('1990', '2009')); stats(('2010', '2026'))
