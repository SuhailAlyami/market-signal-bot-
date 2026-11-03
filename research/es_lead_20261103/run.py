"""ES-led SPX research trigger; not a live lead-lag execution claim."""
import json,hashlib,sys
from pathlib import Path
import numpy as np,pandas as pd
from data_io import readzip
from cfd_causal_reference import Bar
from cfd_acceleration_v4 import acceleration
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def accel(d):
 bars=[Bar(int(x.ts.timestamp()*1000),x.open,x.high,x.low,x.close) for x in d.itertuples()]
 return np.array([acceleration(bars[max(0,i-30):i+1]) for i in range(len(bars))])

def inputs(sp,es):
 d=ev.add_atr(ev.add_structure(sp),'prior20');e=ev.add_atr(ev.add_structure(es),'prior20');a=accel(d);b=accel(e);v=e.volume;median=v.groupby(e.seg).transform(lambda x:x.shift(1).rolling(20).median());rvol=v/median.where(median>0)
 assert np.array_equal(d.ts.values,e.ts.values)
 valid=(d.pos>=30)&(e.pos>=30)&np.isfinite(rvol)&np.isfinite(rvol.groupby(e.seg).shift(1));live=np.where((a==0)&(rvol>=1.5),b,0);lb=pd.Series(b).groupby(e.seg).shift(1).fillna(0).values.astype(int);lr=rvol.groupby(e.seg).shift(1);lag=np.where((a==0)&(lr>=1.5),lb,0)
 return d,{'SPX_ACCEl_baseline':a,'ES_lead_same_close':live,'ES_lead_lag1':lag},valid.values

def select(d,raw,mask):
 ids=[];last=None
 for i in np.flatnonzero(mask&(raw!=0)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);last=now
 return np.array(ids,int)

def main():
 cfg={'hypothesis':'ES original ACCEL v4 with own rvol>=1.5 prior20median can trigger SPX direction only when SPX ACCEL is zero at decision','primary':'same closed minute observed for both ES and SPX; full1minute lag sensitivity separate','lag_sensitivity':'previous ES ACCEL/rvol, current SPX ACCEL zero; shift within contiguous segment only','baseline':'SPX original ACCEL with same available feature universe and cooldown','source':'FirstRate synchronized cash SPX and continuous ES, 12 audited RTH sessions','timing':'minute starts localized US Eastern->UTC; decision plus1minute; no forward fill','cooldown_seconds':600,'target':'SPX 2prior20ATR before1ATR in5contiguousminutes, close and nextopen; ambiguous fail','split':'Oct15-23 development,Oct26-30 consumed later comparison','optimization':'none; one fixed rule plus timing sensitivity; no threshold search','Nov2_and_Nov3':'not loaded','diagnostics':'subsequent SPX ACCEL confirmation is posthoc only; never used to choose signal','status':'RESEARCH_ONLY_NOT_READY'};blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 sp=readzip(sys.argv[1],'SPX_1min_sample.csv');es=readzip(sys.argv[2],'ES_1min_sample.csv');assert len(sp)==len(es)==4680;d,signals,valid=inputs(sp,es)
 for cut in [500,2000,3500]:
  _,short,v=inputs(sp.iloc[:cut].copy(),es.iloc[:cut].copy())
  for key in signals:np.testing.assert_array_equal(short[key],signals[key][:cut])
  np.testing.assert_array_equal(v,valid[:cut])
 cutoff=pd.Timestamp('2026-10-26',tz='UTC');rows=[];exports=[]
 for period,m in [('development',(d.ts<cutoff).values),('later_consumed',(d.ts>=cutoff).values)]:
  mask=valid&m
  for variant,raw in signals.items():
   ids=select(d,raw,mask)
   for entry in ['close','next_open']:
    lab=ev.label(d,entry);ix=ids[lab['status'][ids]==0];side=raw[ix];hit=np.where(side>0,lab['up_c'][ix],lab['dn_c'][ix]);p=(side>0).mean() if len(ix) else 0;mom=np.sign(d.close-d.groupby('seg').close.shift(5)).values[ix];mh=np.where(mom>0,lab['up_c'][ix],lab['dn_c'][ix]);mm=mom!=0
    rows.append({'period':period,'variant':variant,'entry':entry,'signals':len(ids),'scored':len(ix),'hits':int(hit.sum()),'precision':float(hit.mean()) if len(ix) else None,'matched_direction_base':float((p*lab['up_c'][ix]+(1-p)*lab['dn_c'][ix]).mean()) if len(ix) else None,'same_time_momentum_hits':int(mh[mm].sum()),'same_time_momentum_n':int(mm.sum())})
   for i in ids:
    dr=int(raw[i]);confirm=None
    for k in range(1,4):
     if i+k>=len(d) or d.seg.iloc[i+k]!=d.seg.iloc[i]:break
     if signals['SPX_ACCEl_baseline'][i+k]==dr:confirm=k;break
    exports.append({'period':period,'variant':variant,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':dr,'SPX_last5_directional_points':float(dr*(d.close.iloc[i]-d.close.iloc[i-5])),'SPX_last5_directional_ATR':float(dr*(d.close.iloc[i]-d.close.iloc[i-5])/d.atr.iloc[i]),'SPX_confirmation_within3_posthoc_minutes':confirm})
 (P/'RESULT.json').write_text(json.dumps({'rows':rows,'prefix_checks':3,'status':'NOT_READY'},indent=2));pd.DataFrame(exports).to_csv(P/'signals_derived.csv',index=False);print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()
