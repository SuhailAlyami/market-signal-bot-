"""Tradable gap-continuation test. Entry at the 09:30 open in the gap direction, exit at the close.
Gap g = (open - prev_close)/m, m = prev_close*VIX_prev/100/sqrt(252) (known before the open).
Rule chosen on TRAIN 2010-2019 only; TEST 2020-01..2026-11-13 is reported once. Cost 1 SPX point round trip."""
import gzip, json, math, random, statistics as st, sys
from datetime import datetime, timezone
D='vrp/research/volatility_premium_20261115/'
def load(n):
    r=json.load(gzip.open(D+n))['chart']['result'][0]; q=r['indicators']['quote'][0]
    out={}
    for i,t in enumerate(r['timestamp']):
        v=[q[k][i] for k in ('open','high','low','close')]
        if None not in v: out[datetime.fromtimestamp(t,timezone.utc).date()]=v
    return out
spx,vix=load('GSPC_1d.json.gz'),load('VIX_1d.json.gz')
days=sorted(d for d in spx if d.year>=2009)
rows=[]
for a,b in zip(days,days[1:]):
    if a not in vix: continue
    pc=spx[a][3]; o,h,l,c=spx[b]
    if abs(o-pc)<1e-9: continue           # bad open (=prev close)
    m=pc*vix[a][3]/100/math.sqrt(252)
    rows.append(dict(d=b,g=(o-pc)/m,m=m,o=o,h=h,l=l,c=c,y=b.year))
train=[r for r in rows if 2010<=r['y']<=2019]; test=[r for r in rows if r['y']>=2020]
COST=1.0
def pnl(r,side): return side*(r['c']-r['o'])-COST
def trades(S,t):
    return [(r,1 if r['g']>0 else -1) for r in S if abs(r['g'])>=t]
def summ(T):
    p=[pnl(r,s) for r,s in T]
    if not p: return dict(n=0)
    wins=sum(x>0 for x in p)
    se=st.pstdev(p)/math.sqrt(len(p))
    return dict(n=len(p),win=round(100*wins/len(p),1),avg=round(st.mean(p),2),ci=(round(st.mean(p)-1.96*se,2),round(st.mean(p)+1.96*se,2)),total=round(sum(p)),
                worst=round(min(p),1),best=round(max(p),1))
print('rows',len(rows),'train',len(train),'test',len(test))
print('TRAIN threshold scan (choose here only):')
best=None
for t in (0.1,0.2,0.3,0.5):
    s=summ(trades(train,t)); print(' t',t,s)
    if s['n']>=100 and (best is None or s['avg']>best[1]): best=(t,s['avg'])
t=best[0]; print('CHOSEN t =',t)
T=trades(test,t); s=summ(T); print('TEST', s)
# separate sides
print(' TEST long (gap up) ',summ([x for x in T if x[1]==1]))
print(' TEST short (gap dn)',summ([x for x in T if x[1]==-1]))
# baseline: same days, random direction (1000 draws) and always-long
random.seed(7)
base=[sum(pnl(r,random.choice((1,-1))) for r,_ in T)/len(T) for _ in range(2000)]
base.sort(); print(' random-dir avg p5/p50/p95',round(base[100],2),round(base[1000],2),round(base[1900],2))
print(' always-long same days',summ([(r,1) for r,_ in T]))
print(' per year:'); 
for y in sorted({r['y'] for r,_ in T}): print('  ',y,summ([x for x in T if x[0]['y']==y]))
# in m units and adverse excursion
mae=[ (r['o']-r['l'] if s==1 else r['h']-r['o'])/r['m'] for r,s in T]
mfe=[ (r['h']-r['o'] if s==1 else r['o']-r['l'])/r['m'] for r,s in T]
q=lambda a,p: sorted(a)[int(p*len(a))]
print(' adverse excursion (m units) median/p75/p90',round(q(mae,.5),2),round(q(mae,.75),2),round(q(mae,.9),2))
print(' favorable excursion (m units) median/p75',round(q(mfe,.5),2),round(q(mfe,.75),2))
print(' avg m points in test',round(st.mean(r['m'] for r,_ in T),1), ' last day',test[-1]['d'])
print('\n-- sensitivity (NOT used for selection): other thresholds on TEST')
for tt in (0.1,0.2,0.3,0.7,1.0): print('  t',tt,summ(trades(test,tt)))
print('\n-- 0DTE ATM option model (rough: premium = 0.4*m, Black-Scholes ATM approx with VIX as IV, no skew; held to close)')
for k,lab in ((0.4,'ATM buy'),):
    p=[max(s*(r['c']-r['o']),0)-k*r['m']-0.5 for r,s in T]
    se=st.pstdev(p)/math.sqrt(len(p)); print('  ',lab,'avg',round(st.mean(p),2),'ci',(round(st.mean(p)-1.96*se,2),round(st.mean(p)+1.96*se,2)),'win',round(100*sum(x>0 for x in p)/len(p),1))
# debit spread ATM / ATM+0.5m : payoff capped at 0.5m, cost approx 0.4m - value of OTM(0.5m) ~ 0.4m*... approximate OTM premium via normal: E[max(X-k,0)], X~N(0,m)
from math import exp,sqrt,pi,erf
def otm(km): # premium in m units for strike k*m, sigma=m
    phi=exp(-km*km/2)/sqrt(2*pi); Phi=0.5*(1+erf(km/sqrt(2))); return phi-km*(1-Phi)
for w in (0.5,1.0):
    cost=otm(0)-otm(w)
    p=[min(max(s*(r['c']-r['o']),0),w*r['m'])-cost*r['m']-1.0 for r,s in T]
    se=st.pstdev(p)/math.sqrt(len(p)); print(f'   debit spread ATM/+{w}m (cost {cost:.2f}m) avg',round(st.mean(p),2),'ci',(round(st.mean(p)-1.96*se,2),round(st.mean(p)+1.96*se,2)),'win',round(100*sum(x>0 for x in p)/len(p),1))
