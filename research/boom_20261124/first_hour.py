"""After the first hour (10:30 NY): where will the day's high/low end up, and is a big rest-of-day move likely?
SPX hourly (Yahoo) Dec 2023 - Nov 2026. Fit/select on sessions before 2025-01-01, test on 2025-01..2026-11 once."""
import json,gzip,math,datetime as dt
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
H=hourly('GSPC_1h_730d.json.gz'); D=sorted(H)
rows=[]
for p,d in zip(D,D[1:]):
    b=H[d]
    if p not in vix or b[0][0]!=dt.time(9,30) or len(b)<6: continue
    pc=H[p][-1][4]; m=pc*vix[p]/100/math.sqrt(252)
    t,o,h1,l1,c1=b[0]
    hi=max(x[2] for x in b); lo=min(x[3] for x in b); cl=b[-1][4]
    rows.append(dict(d=d,m=m,o=o,h1=h1,l1=l1,c1=c1,hi=hi,lo=lo,cl=cl,r1=(h1-l1)/m,
                     ext_up=(hi-h1)/m, ext_dn=(l1-lo)/m, rest=abs(cl-c1)/m))
tr=[x for x in rows if x['d']<dt.date(2025,1,1)]; te=[x for x in rows if x['d']>=dt.date(2025,1,1)]
print('sessions train',len(tr),'test',len(te))
A=lambda S,k: np.array([x[k] for x in S])
# 1) does the first-hour high/low hold as the day's extreme?
for S,n in ((tr,'TRAIN'),(te,'TEST')):
    print(n,'P(day high > 1st-hour high) %.0f%%  P(day low < 1st-hour low) %.0f%%  P(both) %.0f%%'%(
        100*(A(S,'ext_up')>0).mean(),100*(A(S,'ext_dn')>0).mean(),100*((A(S,'ext_up')>0)&(A(S,'ext_dn')>0)).mean()))
# 2) extension levels: quantiles of extension beyond the first-hour extreme, in m, fitted on TRAIN; coverage on TEST
for side in ('ext_up','ext_dn'):
    for q in (0.7,0.9):
        k=np.quantile(A(tr,side),q); cov=(A(te,side)<=k).mean()
        print(f'{side}: train q{int(q*100)} = {k:.2f} m -> TEST coverage {100*cov:.0f}% (target {int(q*100)}%)')
# 3) first-hour range as early warning of a big rest-of-day move (|close - 10:30| >= 0.5 m)
big=lambda S: A(S,'rest')>=0.5
for S,n in ((tr,'TRAIN'),(te,'TEST')):
    r1=A(S,'r1'); b=big(S)
    t1,t2=np.quantile(A(tr,'r1'),[1/3,2/3])
    print(n,'big rest-of-day move rate: overall %.0f%% | small 1st hour %.0f%% | mid %.0f%% | wide 1st hour %.0f%%'%(
        100*b.mean(),100*b[r1<t1].mean(),100*b[(r1>=t1)&(r1<t2)].mean(),100*b[r1>=t2].mean()), ' n per tercile ~',len(S)//3)
