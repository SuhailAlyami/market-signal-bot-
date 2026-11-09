"""Fixed regularized learner combines18 research models and technical/volume inputs."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import early_move_eval_openfix as ev
from data_io import readzip
from features import technical,patterns
P=Path(__file__).resolve().parent

def select(d,candidate,side,mask):
 ids=[];last=None;seg=None
 for i in np.flatnonzero(candidate&mask):
  t=d.ts.iloc[i].timestamp();g=d.seg.iloc[i]
  if last is None or g!=seg or t-last>=600:ids.append(i);last=t;seg=g
 return np.array(ids,int),side[np.array(ids,int)]

def main():
 cfg={'inputs':'18 unchanged previous Python research model signals plus returns/EMA/RSI/MACD/channel/efficiency/body/wicks/engulf/doji and3ES-volume features','goal':'30minute SPX endpoint direction, no candle-by-candle alerts; only existing-model event candidates, shared10min cooldown','fit':'Oct15..21 five sessions with same-session30min labels','calibration':'Oct22..23 score threshold only, labels not used','later':'Oct26..30 five consumed sessions, exploratory not untouched','model':'StandardScaler plus LogisticRegression C=.1 max_iter2000 seed42, fixed no tuning','comparisons':['majority18 baseline','learned direction on all event times','learned direction only if max score>=calibration90th percentile on event times'],'warmup':'60contiguous minutes for price/channel inputs; same finite-mask across comparisons','unavailable_inputs':'No synchronized12day VIX/options/orderbook/news; never invent or forward-fill these','status':'NOT_READY'}
 blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');es=readzip(P.parent/'FirstRate_ES_sample.zip','ES_1min_sample.csv');tf=technical(d,es);pf=patterns(d);f=pd.concat([tf,pf],axis=1);valid=np.isfinite(f.values).all(1);candidate=(pf.values!=0).any(1);votes=pf.sum(axis=1).values;majority=np.sign(votes).astype(int)
 y=np.zeros(len(d),int);ok=np.zeros(len(d),bool)
 for i in range(len(d)-30):
  if d.seg.iloc[i]==d.seg.iloc[i+30]:delta=d.close.iloc[i+30]-d.close.iloc[i];y[i]=int(delta>0);ok[i]=delta!=0
 # Flat30minute outcomes are excluded from fit but scored as failure for all candidates in eval.
 horizon=np.array([i+30<len(d) and d.seg.iloc[i]==d.seg.iloc[min(i+30,len(d)-1)] for i in range(len(d))])
 train=valid&ok&(d.ts<pd.Timestamp('2026-10-22',tz='UTC')).values;cal=valid&candidate&(d.ts>=pd.Timestamp('2026-10-22',tz='UTC')).values&(d.ts<pd.Timestamp('2026-10-26',tz='UTC')).values;test=valid&(d.ts>=pd.Timestamp('2026-10-26',tz='UTC')).values
 for cut in [500,2000]:
  np.testing.assert_allclose(technical(d.iloc[:cut],es),tf.iloc[:cut],equal_nan=True);np.testing.assert_array_equal(patterns(d.iloc[:cut]),pf.iloc[:cut])
 model=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000,random_state=42)).fit(f.values[train],y[train]);p=np.full(len(d),np.nan);p[valid]=model.predict_proba(f.values[valid])[:,1];score=np.maximum(p,1-p);direction=np.where(p>=.5,1,-1);threshold=float(np.quantile(score[cal],.9));lock={'threshold':threshold,'calibration_events':int(cal.sum()),'fit_rows':int(train.sum()),'feature_names':list(f.columns),'mean':model[0].mean_.tolist(),'scale':model[0].scale_.tolist(),'coefficients':model[1].coef_[0].tolist(),'intercept':float(model[1].intercept_[0]),'score_is_not_calibrated_confidence':True};b=json.dumps(lock,indent=2).encode();(P/'MODEL_LOCK.json').write_bytes(b);(P/'MODEL_LOCK.sha256').write_text(hashlib.sha256(b).hexdigest());rows=[];detail=[]
 for name,raw,dr in [('majority18',candidate&(majority!=0),majority),('learned_all',candidate,direction),('learned_selective',candidate&(score>=threshold),direction)]:
  ids,side=select(d,raw,dr,test);excluded=int((~horizon[ids]).sum());keep=horizon[ids];ix=ids[keep];ss=side[keep];delta=d.close.iloc[ix+30].values-d.close.iloc[ix].values;signed=ss*delta;rate=float((signed>0).mean()) if len(ix) else None;longshare=float((ss>0).mean()) if len(ix) else 0
  rows.append({'model':name,'signals':len(ids),'scored':len(ix),'excluded_horizon':excluded,'hits':int((signed>0).sum()),'rate':rate,'mean_signed_points':float(signed.mean()) if len(ix) else None,'random_direction_same_times':float((longshare*(delta>0)+(1-longshare)*(delta<0)).mean()) if len(ix) else None})
  for i,s,v in zip(ix,ss,signed):detail.append({'model':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'side':int(s),'signed_points':float(v),'hit':bool(v>0)})
 pd.DataFrame(detail).to_csv(P/'signals_derived.csv',index=False);out={'feature_count':len(f.columns),'previous_models':len(pf.columns),'fit_rows':int(train.sum()),'calibration_event_rows':int(cal.sum()),'later_event_rows':int((test&candidate).sum()),'prefix_checks':4,'rows':rows,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
