"""Is the gap continuation an artifact of the SPX index opening print? Compare on the same days:
 (a) SPX index open->close, (b) SPY (tradable ETF) open->close, (c) SPX entering at 10:30 (after the opening print settles).
Hourly Yahoo bars Dec 2023 - Nov 2026 (all inside the TEST period). Threshold fixed at 0.5 m (chosen on train). Cost: 1 SPX pt / 0.1 SPY $."""
import json,gzip,math,statistics as st,datetime as dt
from zoneinfo import ZoneInfo
NY=ZoneInfo('America/New_York'); H='data_history-20261114/history/'
def hourly(f):
    r=json.load(gzip.open(H+f))['chart']['result'][0]; q=r['indicators']['quote'][0]; days={}
    for i,t in enumerate(r['timestamp']):
        if None in (q['open'][i],q['close'][i]): continue
        x=dt.datetime.fromtimestamp(t,NY); days.setdefault(x.date(),[]).append((x.time(),q['open'][i],q['close'][i]))
    return days
def vixd():
    r=json.load(gzip.open('vrp/research/volatility_premium_20261115/VIX_1d.json.gz'))['chart']['result'][0]
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date():c for t,c in zip(r['timestamp'],r['indicators']['quote'][0]['close']) if c}
spx,spy,vix=hourly('GSPC_1h_730d.json.gz'),hourly('SPY_1h_730d.json.gz'),vixd()
D=sorted(set(spx)&set(spy))
res={'spx_open':[],'spy_open':[],'spx_1030':[],'spy_1030':[]}
for a,b in zip(D,D[1:]):
    if a not in vix: continue
    for name,src,cost in (('spx',spx,1.0),('spy',spy,0.1)):
        pc=src[a][-1][2]; bars=src[b]
        if bars[0][0]!=dt.time(9,30): continue
        o=bars[0][1]; c=bars[-1][2]; o1030=bars[0][2]
        m=pc*vix[a]/100/math.sqrt(252); g=(o-pc)/m
        if abs(g)<0.5: continue
        s=1 if g>0 else -1
        k=10.0 if name=='spy' else 1.0          # SPY $ -> ~SPX points
        res[name+'_open'].append((b,k*(s*(c-o)-cost)))
        res[name+'_1030'].append((b,k*(s*(c-o1030)-cost)))
for k,v in res.items():
    p=[x for _,x in v]; se=st.pstdev(p)/math.sqrt(len(p))
    print(f"{k:9s} n={len(p):3d} win={100*sum(x>0 for x in p)/len(p):5.1f}% avg={st.mean(p):6.2f} SPX-pt ci=({st.mean(p)-1.96*se:6.2f},{st.mean(p)+1.96*se:6.2f}) total={sum(p):7.0f}")
