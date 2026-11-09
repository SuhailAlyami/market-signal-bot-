"""Fixed closed5min price-level context on unchanged wave candidates."""
import importlib.util,sys,json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'direction_level_audit'))
from audit import confirmed,early,evaluate

def context(d):
 # Group by continuity segment and wall-clock5min block; only full groups used.
 keys=d.ts.dt.floor('5min');blocks=[]
 for (seg,t),g in d.groupby([d.seg,keys],sort=False):
  if len(g)==5 and g.ts.iloc[0]==t and g.ts.iloc[-1]==t+pd.Timedelta(minutes=4):blocks.append({'seg':seg,'available':t+pd.Timedelta(minutes=5),'level':float(g.close.mean())})
 if not blocks:return np.zeros(len(d),int)
 b=pd.DataFrame(blocks);b['previous']=b.groupby('seg')['level'].shift(1);b['direction']=np.sign(b['level']-b['previous'])
 out=np.zeros(len(d),int)
 for seg,g in d.groupby('seg'):
  q=b[b.seg==seg]
  if q.empty:continue
  joined=pd.merge_asof(pd.DataFrame({'available':g.ts+pd.Timedelta(minutes=1),'i':g.index}),q[['available','direction']],on='available',direction='backward');out[joined.i.to_numpy()]=joined.direction.fillna(0).astype(int)
 return out

def main():
 cfg={'hypothesis':'Filter unchanged confirmed/early wave signals by agreeing movement between means of last two COMPLETE5minute close blocks; no threshold or parameter sweep','availability':'5min block available at block end; minute decision at timestamp+1minute; exclude incomplete blocks; reset at segments','target':'same30minute endpoint direction audit, not trade success','filtering':'postfilter original candidates only; original state not rerun after rejection; no new replacement entries','sample':'12 consumed sessions, later5 descriptive only; chosen posthoc','status':'NOT_READY'}
 blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 d=confirmed.ev.add_atr(confirmed.ev.add_structure(confirmed.readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');ctx=context(d)
 for cut in [500,2000,3500]:assert np.array_equal(context(d.iloc[:cut]),ctx[:cut])
 out=[]
 for name,m in [('confirmed',confirmed),('early',early)]:
  allwaves=m.detect(d)
  for variant,ww in [('original',allwaves),('agree5minute', [w for w in allwaves if ctx[w['i']]==w['side']])]:
   rows,excluded=evaluate(d,ww)
   for period in ['earlier','later']:
    rr=[x for x in rows if x['period']==period];n=len(rr);p=np.mean([x['side']==1 for x in rr]) if n else 0;delta=np.array([x['delta_points'] for x in rr]);hits=sum(x['direction_correct'] for x in rr)
    out.append({'model':name,'variant':variant,'period':period,'n':n,'hits':hits,'rate':hits/n if n else None,'same_time_random_direction_expected':float(np.mean(p*(delta>0)+(1-p)*(delta<0))) if n else None,'mean_signed_points':float(np.mean([x['signed_delta_points'] for x in rr])) if n else None})
 result={'rows':out,'prefix_checks':3,'status':'NOT_READY','warning':'Postfilter on consumed sample; no independence, significance, causal attribution or options profit claim.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
