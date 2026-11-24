"""Does the first hour's direction predict the rest of the day (10:30 -> close)? SPY hourly (tradable), Dec 2023-Nov 2026.
Rules chosen on sessions before 2025-01-01; test 2025-01..2026-11 once. Cost 0.02 $ per SPY round trip (~0.2 SPX pt)."""
import json,gzip,math,statistics as st,datetime as dt
import numpy as np
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York')
def hourly(f):
    r=json.load(gzip.open('data_history-20261114/history/'+f))['chart']['result'][0]; q=r['indicators']['quote'][0]; d={}
    for i,t in enumerate(r['timestamp']):
        v=[q[k][i] for k in ('open','high','low','close')]
        if None in v: continue
        x=dt.datetime.fromtimestamp(t,NY); d.setdefault(x.date(),[]).append((x.time(),*v))
    return d
r=json.load(gzip.open('vrp/research/volatility_premium_20261115/VIX_1d.json.gz'))['chart']['result'][0]
vix={dt.datetime.fromtimestamp(t,dt.timezone.utc).date():c for t,c in zip(r['timestamp'],r['indicators']['quote'][0]['close']) if c}
H=hourly('SPY_1h_730d.json.gz'); D=sorted(H); rows=[]
for p,d in zip(D,D[1:]):
    b=H[d]
    if p not in vix or b[0][0]!=dt.time(9,30) or len(b)<6: continue
    pc=H[p][-1][4]; m=pc*vix[p]/100/math.sqrt(252); o=b[0][1]; c1=b[0][4]; cl=b[-1][4]
    rows.append(dict(d=d,f=(c1-o)/m,g=(o-pc)/m,rest=cl-c1,m=m))
def run(S,thr,mode):
    p=[]
    for x in S:
        if abs(x['f'])<thr: continue
        s=(1 if x['f']>0 else -1)*(1 if mode=='follow' else -1)
        p.append(10*(s*x['rest']-0.02))
    if len(p)<2: return None
    se=st.stdev(p)/math.sqrt(len(p))
    return dict(n=len(p),win=round(100*sum(v>0 for v in p)/len(p)),avg=round(st.mean(p),2),ci=(round(st.mean(p)-1.96*se,1),round(st.mean(p)+1.96*se,1)))
tr=[x for x in rows if x['d']<dt.date(2025,1,1)]; te=[x for x in rows if x['d']>=dt.date(2025,1,1)]
best=None
for mode in ('follow','fade'):
    for thr in (0.1,0.2,0.3,0.5):
        r_=run(tr,thr,mode); print('TRAIN',mode,thr,r_)
        if r_ and r_['n']>=40 and (best is None or r_['avg']>best[2]): best=(mode,thr,r_['avg'])
print('CHOSEN',best[:2]); print('TEST',best[:2],run(te,best[1],best[0]))
print('TEST all (not for selection):'); [print('  ',m_,t,run(te,t,m_)) for m_ in ('follow','fade') for t in (0.1,0.2,0.3,0.5)]
