"""SPX ACCEL with real same-time ES December2026 bar volume. Research only."""
import sys,json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
import early_move_eval_openfix as ev
from cfd_causal_reference import Bar
from cfd_acceleration_v4 import acceleration
P=Path(__file__).resolve().parent

def volume_features(es):
 es=es.copy();es['ts']=pd.to_datetime(es.ts,utc=True)
 if es.ts.duplicated().any() or not es.ts.is_monotonic_increasing:raise ValueError('ES timestamp order/duplicate')
 if not np.isfinite(es.volume).all() or (es.volume<0).any():raise ValueError('invalid volume')
 es['seg']=(es.ts.diff().dt.total_seconds()!=60).cumsum();prior=es.groupby('seg').volume.transform(lambda x:x.shift(1).rolling(20).median());es['rvol']=es.volume/prior.where(prior>0)
 es['rvol_lag1']=es.groupby('seg').rvol.shift(1)
 return es

def cooldown(d,raw,mask):
 ids=[];last=None
 for i in np.flatnonzero(mask&(raw!=0)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);last=now
 return np.array(ids,int)

def main():
 c={'hypothesis':'ACCEL v4 original on SPX with ES Dec2026 volume>=1.5 prior20 median; no other ES price/direction filter','price_source':'IBKR SPX IND CBOE416904','volume_source':'IBKR ES FUT CME515416632 expiry20261218; not SPX volume','synchronization':'exact same bar-start UTC; standard1min; no forward fill; restrict ES reference to SPX regular-session timestamps available in archive','reference':'previous20 volumes only, reset every non60secondstep; median must be positive','lag_sensitivity':'separate lag1 ES rvol, threshold unchanged','common_baseline':'all comparisons require finite rvol AND lag1; filter applied before shared600sec cooldown','evaluation':'2prior20ATR before1ATR in5contiguousminutes; close primary nextopen secondary; ambiguous fails','periods':['Oct29-30 available native overlap, consumed','Nov2 diagnostic consumed'],'optimization':'single fixed threshold; no tuning based on results','status':'RESEARCH_ONLY_NOT_READY'};b=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 a=pd.read_csv(P.parent/'recovered_spx_research/SPX_1m.csv');n=pd.read_csv(P.parent/'nov2_final_review/SPX_20261102.csv');sp=pd.concat([a,n],ignore_index=True);sp['ts']=pd.to_datetime(sp.pop('timestamp'),utc=True,format='ISO8601');assert not sp.ts.duplicated().any();sp=sp.sort_values('ts').reset_index(drop=True);d=ev.add_atr(ev.add_structure(sp),'prior20')
 es=json.loads((P/'ES_202612_raw.json').read_text());es=pd.DataFrame({'ts':pd.to_datetime(es['time'],utc=True),'open':es['open'],'high':es['high'],'low':es['low'],'close':es['close'],'volume':es['volume']});raw_es_rows=len(es);es=es[es.ts.isin(d.ts)].reset_index(drop=True);es=volume_features(es);joined=d.merge(es[['ts','volume','rvol','rvol_lag1']],on='ts',how='left',validate='one_to_one');eligible=np.isfinite(joined.rvol)&np.isfinite(joined.rvol_lag1)
 bars=[Bar(int(r.ts.timestamp()*1000),r.open,r.high,r.low,r.close) for r in d.itertuples()];raw=np.array([acceleration(bars[max(0,i-30):i+1]) for i in range(len(bars))]);rows=[];exports=[]
 for group,period in [('Oct29_30_consumed',(d.ts<pd.Timestamp('2026-11-02',tz='UTC')).values),('Nov2_consumed',(d.ts>=pd.Timestamp('2026-11-02',tz='UTC')).values)]:
  universe=eligible.values&period
  for name,flt in [('baseline',np.ones(len(d),bool)),('ES_rvol',joined.rvol.values>=1.5),('ES_rvol_lag1',joined.rvol_lag1.values>=1.5)]:
   ids=cooldown(d,raw,universe&flt)
   for entry in ['close','next_open']:
    l=ev.label(d,entry);ix=ids[l['status'][ids]==0];dr=raw[ix];hits=np.where(dr>0,l['up_c'][ix],l['dn_c'][ix]);p=(dr>0).mean() if len(ix) else 0;base=float((p*l['up_c'][ix]+(1-p)*l['dn_c'][ix]).mean()) if len(ix) else None
    rows.append({'period':group,'variant':name,'entry':entry,'eligible_price_rows':int(universe.sum()),'signals':len(ids),'scored':len(ix),'hits':int(hits.sum()),'precision':float(hits.mean()) if len(ix) else None,'matched_direction_base':base})
   for i in ids:exports.append({'period':group,'variant':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':int(raw[i]),'ES_volume':float(joined.volume.iloc[i]),'rvol':float(joined.rvol.iloc[i]),'rvol_lag1':float(joined.rvol_lag1.iloc[i])})
 audit={'raw_ES_rows':raw_es_rows,'matched_ES_SPX_rows':len(es),'common_finite_rvol_rows':int(eligible.sum()),'ES_positive_volume_rows':int((es.volume>0).sum()),'dates':es.groupby(es.ts.dt.strftime('%Y-%m-%d')).size().to_dict(),'source_contract':'ES Dec2026 CME515416632','assumption':'shared timestamps denote same minute start; no inference of trade side or IV; historical research only'}
 (P/'AUDIT.json').write_text(json.dumps(audit,indent=2));(P/'RESULT.json').write_text(json.dumps(rows,indent=2));pd.DataFrame(exports).to_csv(P/'signals_derived.csv',index=False);joined.to_csv(P/'synchronized.csv',index=False);print(json.dumps(audit,indent=2));print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
