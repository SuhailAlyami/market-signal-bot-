"""Combine frozen separately-trained timeframes using causal availability only."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'multiframe_unified'))
import run as base

FRAMES={'FIVE_MINS':5,'FIFTEEN_MINS':15,'THIRTY_MINS':30,'ONE_DAY':None}
def asof_direction(decisions,available):
 return pd.merge_asof(decisions.sort_values('available'),available.sort_values('available'),on='available',direction='backward',allow_exact_matches=True)

def frame(name,minutes):
 root=base.P;sp=base.raw(root/'raw'/('SPX_'+name+'.json'));es=base.raw(root/'raw'/('ES_'+name+'.json'));d,ee=base.prepare(sp,es,minutes);tf=base.ft.technical(d,ee);pf=base.ft.patterns(d);f=pd.concat([tf,pf],axis=1);variant='price_patterns' if minutes is None else 'price_patterns_volume';lockpath=root/(name+'_'+variant+'_MODEL.json');lock=json.loads(lockpath.read_text());X=f[lock['features']].values;valid=np.isfinite(X).all(1);p=np.full(len(d),np.nan);z=((X[valid]-np.array(lock['mean']))/np.array(lock['scale']))@np.array(lock['coefficients'])+lock['intercept'];p[valid]=1/(1+np.exp(-np.clip(z,-30,30)));direction=np.where(valid,np.where(p>=.5,1,-1),0)
 return d,pf,direction,hashlib.sha256(lockpath.read_bytes()).hexdigest()

def main():
 cfg={'purpose':'Frozen multi-timeframe agreement; no fitting or threshold tuning','primary':'5min price+patterns+ESvolume event direction','comparisons':['primary alone','5m15m30m same direction','5m15m30m plus daily same direction'],'availability':'last completed bar whose available timestamp <= primary decision; invalid latest features produce direction0, no carry of older valid score','daily':'previous available daily close prediction is context for5min, not same target; daily volume remains blocked','period':'Oct29..Nov2 common primary evaluation3sessions; consumed exploratory only','target':'SPX30minute endpoint same session6primary bars','cooldown':'10primary trading bars after filtering; event sets differ','status':'NOT_READY'}
 b=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest());data={};hashes={}
 for name,minutes in FRAMES.items():
  d,pf,dr,sha=frame(name,minutes);data[name]=(d,pf,dr);hashes[name]=sha
 d,pf,primary=data['FIVE_MINS'];q=pd.DataFrame({'available':d.available,'i':d.index,'primary':primary})
 for name in ['FIFTEEN_MINS','THIRTY_MINS','ONE_DAY']:
  hd,hf,dr=data[name];h=pd.DataFrame({'available':hd.available,'direction_'+name:dr,'source_available_'+name:hd.available});q=asof_direction(q,h)
  assert ((q['source_available_'+name].isna())|(q['source_available_'+name]<=q.available)).all()
 q=q.sort_values('i');candidate=(pf.values!=0).any(1)&(primary!=0)&(d.session>='2026-10-29').values;intraday=candidate&(q.direction_FIFTEEN_MINS.values==primary)&(q.direction_THIRTY_MINS.values==primary);daily=intraday&(q.direction_ONE_DAY.values==primary);rows=[];details=[]
 for name,mask in [('5m_only',candidate),('agree_intraday',intraday),('agree_intraday_daily',daily)]:
  ids=base.select(d,mask);good=np.array([i+6<len(d) and d.seg.iloc[i]==d.seg.iloc[i+6] and d.session.iloc[i]==d.session.iloc[i+6] for i in ids],dtype=bool);ix=ids[good];delta=d.close.iloc[ix+6].values-d.close.iloc[ix].values;side=primary[ix];signed=side*delta;n=len(ix);p=float((side>0).mean()) if n else 0
  rows.append({'rule':name,'signals':len(ids),'scored':n,'excluded_horizon':len(ids)-n,'hits':int((signed>0).sum()),'rate':float((signed>0).mean()) if n else None,'mean_signed_points':float(signed.mean()) if n else None,'random_direction_same_times':float((p*(delta>0)+(1-p)*(delta<0)).mean()) if n else None})
  for i,pts in zip(ix,signed):details.append({'rule':name,'decision_Riyadh':str(d.available.iloc[i].tz_convert('Asia/Riyadh')),'side':int(primary[i]),'signed_points':float(pts),'15m_available':str(q.source_available_FIFTEEN_MINS.iloc[i]),'30m_available':str(q.source_available_THIRTY_MINS.iloc[i]),'daily_available':str(q.source_available_ONE_DAY.iloc[i])})
 pd.DataFrame(details).to_csv(P/'signals_derived.csv',index=False);(P/'MODEL_INPUT_HASHES.json').write_text(json.dumps(hashes,indent=2));out={'rows':rows,'eligible_primary_events':int(candidate.sum()),'primary_events_with_valid_daily':int((candidate&(q.direction_ONE_DAY.values!=0)).sum()),'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
