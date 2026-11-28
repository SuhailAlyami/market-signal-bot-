import gzip, csv, glob, os, sys, statistics as st
from datetime import datetime
from zoneinfo import ZoneInfo
NY = ZoneInfo('America/New_York'); P = sys.argv[1]
days = {}
for f in sorted(glob.glob(f'{P}/*.csv.gz')):
    rows = list(csv.DictReader(gzip.open(f, 'rt')))
    b = {}
    for r in rows:
        t = datetime.fromisoformat(r['timestamp']).astimezone(NY)
        b[t.strftime('%H:%M')] = (float(r['Open']), float(r['High']), float(r['Low']), float(r['Close']))
    if '09:30' in b and '15:59' in b and '15:30' in b: days[os.path.basename(f)[:10]] = b
ds = sorted(days); ltd = {ds[i] for i in range(len(ds)-1) if ds[i][:7] != ds[i+1][:7]}
print('days', len(ds), 'LTD', len(ltd))
def seg(b, a, z): return b[z][3] - b[a][0]
for name, A, Z in (('last 60m', '15:00', '15:59'), ('last 30m', '15:30', '15:59'), ('MOC 15:50-16', '15:50', '15:59')):
    for grp in ('LTD', 'other'):
        xs = [seg(days[d], A, Z) for d in ds if (d in ltd) == (grp == 'LTD') and A in days[d]]
        print(f'{name:13s} {grp:5s} n={len(xs):3d} mean|move| {st.mean(abs(x) for x in xs):5.1f} pts  up {100*sum(x>0 for x in xs)/len(xs):.0f}%')
# LTD: last-30m direction vs month-to-date (first open of month -> 15:30)
first = {}
for d in ds: first.setdefault(d[:7], days[d]['09:30'][0])
for d in sorted(ltd):
    b = days[d]; mtd = b['15:30'][0]/first[d[:7]]-1
    print(d, f'MTD {100*mtd:+.1f}%', f'last30 {seg(b,"15:30","15:59"):+.1f}', f'day O->C {b["15:59"][3]-b["09:30"][0]:+.1f}')
