"""Fixed ES volume + bar-proxy anchored VWAP confirmation for native SPX ACCEL."""
import io,json,hashlib,zipfile,sys
from pathlib import Path
import numpy as np,pandas as pd
import early_move_eval_openfix as ev
from cfd_causal_reference import Bar
from cfd_acceleration_v4 import acceleration
P=Path(__file__).resolve().parent

def readzip(path,name):
 d=pd.read_csv(io.BytesIO(zipfile.ZipFile(path).read(name)));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 if d.ts.duplicated().any() or not d.ts.is_monotonic_increasing:raise ValueError('timestamp integrity')
 for col in ['open','high','low','close']:
  if not np.isfinite(d[col]).all() or (d[col]<=0).any():raise ValueError('price validity')
 if not ((d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))).all():raise ValueError('OHLC integrity')
 if 'volume' in d and (not np.isfinite(d.volume).all() or (d.volume<=0).any()):raise ValueError('volume integrity')
 loc=d.ts.dt.tz_convert('America/New_York');mins=loc.dt.hour*60+loc.dt.minute
 return d[(mins>=570)&(mins<960)&(loc.dt.dayofweek<5)].reset_index(drop=True)

def es_features(d):
 d=d.copy();day=d.ts.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');d['seg']=(d.ts.diff().dt.total_seconds()!=60).cumsum();median=d.groupby('seg').volume.transform(lambda x:x.shift(1).rolling(20).median());d['rvol']=d.volume/median.where(median>0)
 proxy=(d.high+d.low+d.close)/3;pv=proxy*d.volume;d['vwap']=pv.groupby(day).cumsum()/d.volume.groupby(day).cumsum();d['vwap_prior5']=d.vwap.groupby(day).shift(5)
 loc=d.ts.dt.tz_convert('America/New_York');mins=loc.dt.hour*60+loc.dt.minute-570;count=d.groupby(day).cumcount();d['anchor_complete']=(count==mins)&d.ts.groupby(day).transform('min').dt.tz_convert('America/New_York').dt.strftime('%H:%M').eq('09:30')
 # After the first missing minute count stays lower, invalidating the anchor for the rest of that day.
 return d

def cooldown(d,raw,mask):
 ids=[];last=None
 for i in np.flatnonzero(mask&(raw!=0)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);last=now
 return np.array(ids,int)

def main():
 c={'hypothesis':'ACCEL v4 on SPX with ES rvol>=1.5 AND ES close on matching side of ES session VWAP AND VWAP current vs5min ago slope matching signal','VWAP':'HLC3 times minute volume cumulative from NYSE09:30 Eastern; bar proxy not tick VWAP; require every minute since open','reference':'ES previous20 minute median volume only; no forward fill','comparisons':['ACCEL baseline','ACCEL plus fixed RVOL1.5','ACCEL plus RVOL1.5 plus VWAP alignment'],'split':'Oct15-23 development,Oct26-30 consumed later comparison','new_ES_source':'FirstRate free continuous ES sample, contract-adjustment flavor not explicitly identified; compare overlap with IBKR Dec2026','price_source':'FirstRate SPX cash sample; no CFD mixing','evaluation':'unchanged2prior20SMA TR target before1ATR stop in5contiguous minutes; close and nextopen','cooldown':'600seconds shared after filters; common finite feature universe','optimization':'single hypothesis; no parameter scan or later tuning','status':'RESEARCH_ONLY_NOT_READY','Nov2':'not evaluated here','Nov3':'not loaded'};b=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 sp=readzip(sys.argv[1],'SPX_1min_sample.csv');es=readzip(sys.argv[2],'ES_1min_sample.csv');es=es_features(es);d=ev.add_atr(ev.add_structure(sp),'prior20');j=d.merge(es[['ts','close','volume','rvol','vwap','vwap_prior5','anchor_complete']],on='ts',how='left',validate='one_to_one',suffixes=('','_es'));common=np.isfinite(j.rvol)&np.isfinite(j.vwap_prior5)&j.anchor_complete.eq(True)
 bars=[Bar(int(x.ts.timestamp()*1000),x.open,x.high,x.low,x.close) for x in d.itertuples()];raw=np.array([acceleration(bars[max(0,i-30):i+1]) for i in range(len(bars))]);align=((raw==1)&(j.close_es>j.vwap)&(j.vwap>j.vwap_prior5))|((raw==-1)&(j.close_es<j.vwap)&(j.vwap<j.vwap_prior5));cut=pd.Timestamp('2026-10-26',tz='UTC');rows=[];signals=[]
 for period,mask in [('development',(d.ts<cut).values),('later_consumed',(d.ts>=cut).values)]:
  universe=common.values&mask
  for name,flt in [('baseline',np.ones(len(d),bool)),('rvol',j.rvol.values>=1.5),('rvol_vwap',(j.rvol.values>=1.5)&align.values)]:
   ids=cooldown(d,raw,universe&flt)
   for entry in ['close','next_open']:
    lab=ev.label(d,entry);ix=ids[lab['status'][ids]==0];dr=raw[ix];hit=np.where(dr>0,lab['up_c'][ix],lab['dn_c'][ix]);n=len(ix);p=(dr>0).mean() if n else 0
    rows.append({'period':period,'variant':name,'entry':entry,'universe_rows':int(universe.sum()),'signals':len(ids),'scored':n,'hits':int(hit.sum()),'precision':float(hit.mean()) if n else None,'matched_direction_base':float((p*lab['up_c'][ix]+(1-p)*lab['dn_c'][ix]).mean()) if n else None})
   for i in ids:signals.append({'period':period,'variant':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':int(raw[i]),'rvol':float(j.rvol.iloc[i])})
 audit={'SPX_RTH_rows':len(sp),'ES_RTH_rows':len(es),'exact_timestamp_matches':int(j.close_es.notna().sum()),'common_feature_rows':int(common.sum()),'SPX_dates':sp.groupby(sp.ts.dt.strftime('%Y-%m-%d')).size().to_dict(),'ES_dates':es.groupby(es.ts.dt.strftime('%Y-%m-%d')).size().to_dict(),'input_sha256':{Path(f).name:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in sys.argv[1:3]},'timezones':'US Eastern DST localized then UTC; timestamps are bar starts; decision plus1minute'}
 ib=json.loads((P.parent/'spx_es_volume/ES_202612_raw.json').read_text());ib=pd.DataFrame({'ts':pd.to_datetime(ib['time'],utc=True),'close':ib['close'],'volume':ib['volume']});over=es.merge(ib,on='ts',suffixes=('_FR','_IBKR'));audit['ES_overlap_IBKR']={'rows':len(over),'max_abs_close_difference':float((over.close_FR-over.close_IBKR).abs().max()),'same_close_fraction':float((over.close_FR==over.close_IBKR).mean()),'same_volume_fraction':float((over.volume_FR==over.volume_IBKR).mean())}
 for cut in [100,1000,3000]:
  f=es_features(es.iloc[:cut]);np.testing.assert_allclose(f[['rvol','vwap','vwap_prior5']].values,es[['rvol','vwap','vwap_prior5']].iloc[:cut].values,equal_nan=True)
 (P/'AUDIT.json').write_text(json.dumps(audit,indent=2));(P/'RESULT.json').write_text(json.dumps({'rows':rows,'prefix_checks':3,'status':'NOT_READY'},indent=2));pd.DataFrame(signals).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(audit,indent=2));print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
