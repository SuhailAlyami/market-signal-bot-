"""Descriptive same-time direction controls; no independence assumption or p-value."""
import json
import numpy as np,pandas as pd
import run as r
P=r.P
es=r.load(P.parent/'halfminute_lead_audit/ES_raw.json');sp=r.load(P.parent/'halfminute_lead_audit/SPX_raw.json')
d=sp.merge(es,on='ts',suffixes=('_SPX','_ES'),validate='one_to_one')
for name,data in [('SPX',sp),('ES',es)]:
 m=r.ev.add_atr(r.ev.add_structure(r.minute_bars(data)),'prior20');d['atr_'+name]=d.ts.dt.floor('min').map(m.set_index('ts').atr)
d=r.features(d);signals=pd.read_csv(P/'signals_derived.csv');out=[]
for variant,g in signals.groupby('variant',sort=False):
 times=pd.to_datetime(g.decision_Riyadh,utc=True)-pd.Timedelta(seconds=30)
 ids=d.index[d.ts.isin(times)].to_numpy();assert len(ids)==len(g)
 # Align explicitly by source time, never rely on exported row order.
 sides=pd.Series(g.direction.to_numpy(),index=times);side=sides.reindex(pd.DatetimeIndex(d.ts.iloc[ids])).to_numpy()
 for entry in ['close','next_open']:
  actual=r.labels(d,ids,side,entry);up=r.labels(d,ids,np.ones(len(ids),int),entry);dn=r.labels(d,ids,-np.ones(len(ids),int),entry)
  good=np.array([not x['outcome'].startswith('UNSCORABLE') for x in actual]);n=int(good.sum())
  wins=lambda rows:sum(x['outcome']=='TARGET' for x,ok in zip(rows,good) if ok)
  mom=np.where(d.r_SPX.iloc[ids].to_numpy()>=0,1,-1);esmom=np.where(d.r_ES.iloc[ids].to_numpy()>=0,1,-1)
  counts={}
  for a,u,v,ok in zip(actual,up,dn,good):
   if ok:counts[a['outcome']]=counts.get(a['outcome'],0)+1
  out.append({'variant':variant,'entry':entry,'n':n,'actual_hits':wins(actual),'random_same_time_expected_hits':.5*(wins(up)+wins(dn)),'SPX_momentum_hits':wins(r.labels(d,ids,mom,entry)),'ES_momentum_hits':wins(r.labels(d,ids,esmom,entry)),'actual_outcomes':counts})
result={'rows':out,'interpretation':'Descriptive controls only. Same consumed day, overlapping variants, tiny samples; no significance or out-of-sample claim. Momentum zero return assigned long in this control. No parameter changes.','data_access':'TWO_DAYS THIRTY_SECS rejected for both instruments: more than allowed 1000 points; connector has no end-date parameter.','status':'NOT_READY'}
(P/'CONTROLS.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
