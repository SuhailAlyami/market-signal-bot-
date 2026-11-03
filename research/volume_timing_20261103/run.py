"""Price/volume timing experiment; not a directional detector."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
import reference as r
P=Path(__file__).resolve().parent

def timing(d):
 y=np.zeros(len(d),bool);lab=r.ev.label(d,'close');ok=lab['status']==0
 for i in np.flatnonzero(ok):
  e=d.close.iloc[i];a=d.atr.iloc[i];b=d.iloc[i+1:i+6];y[i]=max(b.high.max()-e,e-b.low.min())>=2*a
 return y,ok

def main():
 cfg={'purpose':'Predict 2ATR excursion in either direction over next5minutes ignoring stops, NOT directional signal precision','fit':'Oct15..21 five days','calibration':'Oct22..23 features only','test':'Oct26..30 consumed exploratory five days','threshold':'fixed90th percentile calibration scores, no sweep','model':'same fixed HGB60 leaf7 depth3 minleaf50 l210 lr.05 seed42','cooldown':600,'comparison':'price7 versus price7+ESvolume3, common eligible bars','status':'NOT_READY'}
 b=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 d=r.ev.add_atr(r.ev.add_structure(r.readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');es=r.readzip(P.parent/'FirstRate_ES_sample.zip','ES_1min_sample.csv');pf=r.price_features(d);v=r.volume_features(es);vf=d[['ts']].merge(v,on='ts',how='left',validate='one_to_one').drop(columns='ts');ff=pd.concat([pf,vf],axis=1);valid=np.isfinite(ff.values).all(1);y,ok=timing(d)
 train=valid&ok&(d.ts<pd.Timestamp('2026-10-22',tz='UTC')).values;cal=valid&(d.ts>=pd.Timestamp('2026-10-22',tz='UTC')).values&(d.ts<pd.Timestamp('2026-10-26',tz='UTC')).values;test=valid&ok&(d.ts>=pd.Timestamp('2026-10-26',tz='UTC')).values
 rows=[];lock={};sig=[]
 for name,X in [('price',pf.values),('price_volume',ff.values)]:
  model=HistGradientBoostingClassifier(max_iter=60,max_leaf_nodes=7,max_depth=3,min_samples_leaf=50,l2_regularization=10,learning_rate=.05,early_stopping=False,random_state=42).fit(X[train],y[train]);scores=np.full(len(d),np.nan);scores[valid]=model.predict_proba(X[valid])[:,1];th=float(np.quantile(scores[cal],.90));lock[name]={'threshold':th};ids=[];last=None
  for i in np.flatnonzero(test&(scores>=th)):
   t=d.ts.iloc[i].timestamp()
   if last is None or t-last>=600:ids.append(i);last=t
  ids=np.array(ids,int);daily=[]
  for day in sorted(set(d.ts.iloc[ids].dt.strftime('%Y-%m-%d'))):
   ix=ids[d.ts.iloc[ids].dt.strftime('%Y-%m-%d').values==day];daily.append({'date':day,'n':len(ix),'movement_hits':int(y[ix].sum())})
  rows.append({'model':name,'selected':len(ids),'movement_hits':int(y[ids].sum()),'movement_rate':float(y[ids].mean()) if len(ids) else None,'all_eligible_test_movement_rate':float(y[test].mean()),'eligible_test_n':int(test.sum()),'daily':daily})
  for i in ids:sig.append({'model':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'movement_hit':bool(y[i])})
 (P/'LOCK.json').write_text(json.dumps(lock,indent=2));out={'rows':rows,'train_rows':int(train.sum()),'cal_rows':int(cal.sum()),'status':'NOT_READY','warning':'Movement hit ignores direction and stop; cannot be called trading success. No confidence calibration or new holdout.'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));pd.DataFrame(sig).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
