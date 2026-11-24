"""Close-to-close rules (closes are tradable via MOC; no opening-print artifact). Enter at today's close, exit next close.
Candidates fixed in advance; select on 2000-2019, test 2020-01..2026-11-13 once. Cost 1 SPX pt. Baseline = unconditional
long on all days (equity drift), reported as excess per trade."""
import gzip, json, math, statistics as st, datetime as dt
D='vrp/research/volatility_premium_20261115/'
def load(n):
    r=json.load(gzip.open(D+n))['chart']['result'][0]; q=r['indicators']['quote'][0]
    return {dt.datetime.fromtimestamp(t,dt.timezone.utc).date():q['close'][i] for i,t in enumerate(r['timestamp']) if q['close'][i]}
spx,vix=load('GSPC_1d.json.gz'),load('VIX_1d.json.gz')
days=[d for d in sorted(spx) if d in vix and d.year>=1999]
rows=[]
for i in range(3,len(days)-1):
    d,p=days[i],days[i-1]
    m=spx[p]*vix[p]/100/math.sqrt(252)
    rows.append(dict(d=d,ret=(spx[d]-spx[p])/m, down3=all(spx[days[i-k]]<spx[days[i-k-1]] for k in range(3)),
                     vixjump=vix[d]/vix[p]-1, nxt=spx[days[i+1]]-spx[d]-1.0, y=d.year))
RULES={'down_1m':lambda r:r['ret']<=-1.0,'down_1.5m':lambda r:r['ret']<=-1.5,'three_down':lambda r:r['down3'],
       'vix_jump20':lambda r:r['vixjump']>=0.20,'up_1m_fade':lambda r:r['ret']>=1.0}
def summ(S,rule):
    base=st.mean(x['nxt'] for x in S)
    p=[x['nxt'] for x in S if RULES[rule](x)]
    if len(p)<2: return None
    se=st.stdev(p)/math.sqrt(len(p)); a=st.mean(p)
    if rule=='up_1m_fade': p=[-v-2 for v in p]; a=st.mean(p); base=-base-2   # short after big up (cost already 1 -> 2 incl. sign flip)
    return dict(n=len(p),win=round(100*sum(v>0 for v in p)/len(p)),avg=round(a,2),excess=round(a-base,2),ci=(round(a-1.96*se,1),round(a+1.96*se,1)),base=round(base,2))
tr=[r for r in rows if 2000<=r['y']<=2019]; te=[r for r in rows if r['y']>=2020]
best=None
for k in RULES:
    s=summ(tr,k); print('TRAIN',k,s)
    if s and s['n']>=60 and (best is None or s['excess']>best[1]): best=(k,s['excess'])
print('CHOSEN',best[0]); print('TEST',best[0],summ(te,best[0]))
print('-- all on TEST (not for selection)'); [print('  ',k,summ(te,k)) for k in RULES]
