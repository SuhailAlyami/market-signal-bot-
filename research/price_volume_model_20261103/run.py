"""Fixed paired price vs price+ES-volume model. Exploratory, no threshold scan."""
import json,hashlib,sys
from pathlib import Path
import numpy as np,pandas as pd,sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from data_io import readzip
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def price_features(d):
 f=pd.DataFrame(index=d.index)
 for k in [1,5,15]:f['return'+str(k)+'_ATR']=(d.close-d.groupby('seg').close.shift(k))/d.atr
 f['range_ATR']=(d.high-d.low)/d.atr;f['body_ATR']=(d.close-d.open)/d.atr;f['close_position']=((d.close-d.low)/(d.high-d.low).replace(0,np.nan)).fillna(.5)
 change=d.groupby('seg').close.diff();path=change.abs().groupby(d.seg).transform(lambda x:x.rolling(5).sum());f['efficiency5']=((d.close-d.groupby('seg').close.shift(5)).abs()/path.replace(0,np.nan)).fillna(0)
 f.loc[d.pos<21,:]=np.nan
 return f.replace([np.inf,-np.inf],np.nan)

def volume_features(es):
 es=es.copy();seg=(es.ts.diff().dt.total_seconds()!=60).cumsum();v=es.volume;median=v.groupby(seg).transform(lambda x:x.shift(1).rolling(20).median());mean=v.groupby(seg).transform(lambda x:x.shift(1).rolling(20).mean());r=v/median.where(median>0)
 return pd.DataFrame({'ts':es.ts,'log1p_rvol':np.log1p(r),'log1p_rvol_lag1':np.log1p(r.groupby(seg).shift(1)),'volume5_prior20mean_ratio':v.groupby(seg).transform(lambda x:x.rolling(5).sum())/(5*mean.where(mean>0))})

def select(d,prob,threshold,mask):
 ids=[];sides=[];last=None
 for i in np.flatnonzero(mask):
  if not np.isfinite(prob[i]).all() or prob[i].max()<threshold:continue
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);sides.append(1 if prob[i,0]>=prob[i,1] else -1);last=now
 return np.array(ids,int),np.array(sides,int)

def evaluate(d,ids,dr,entry):
 lab=ev.label(d,entry);ok=lab['status'][ids]==0;ix=ids[ok];side=dr[ok];n=len(ix);hit=np.where(side>0,lab['up_c'][ix],lab['dn_c'][ix]);p=float((side>0).mean()) if n else 0;mom=np.sign(d.close-d.groupby('seg').close.shift(5)).values[ix];mh=np.where(mom>0,lab['up_c'][ix],lab['dn_c'][ix]);mm=mom!=0
 daily=[]
 for day in sorted(set(d.ts.iloc[ix].dt.strftime('%Y-%m-%d'))):
  mask=d.ts.iloc[ix].dt.strftime('%Y-%m-%d').values==day;daily.append({'date':day,'n':int(mask.sum()),'hits':int(hit[mask].sum())})
 return {'entry':entry,'signals':len(ids),'scored':n,'hits':int(hit.sum()),'precision':float(hit.mean()) if n else None,'matched_direction_base':float((p*lab['up_c'][ix]+(1-p)*lab['dn_c'][ix]).mean()) if n else None,'same_time_momentum_hits':int(mh[mm].sum()),'momentum_n':int(mm.sum()),'wilson_descriptive_only':ev.wilson(int(hit.sum()),n) if n else None,'daily':daily}

def main():
 cfg={'fit':'Oct15-21 inclusive five sessions','calibration':'Oct22-23 two sessions; labels unused for cutoff','later':'Oct26-30 five sessions consumed in previous research; exploratory only','hypothesis':'Pair same fixed model with seven SPX price features vs add three ES bar-volume features only; identical common data mask','classifier':{'max_iter':60,'max_leaf_nodes':7,'max_depth':3,'min_samples_leaf':50,'l2_regularization':10,'learning_rate':.05,'early_stopping':False,'random_state':42},'targets':'two binary targets long/short2prior20ATR before1ATR within5contiguousminutes','threshold':'fixed98th percentile of max(long,short) scores on calibration features only, independently for each candidate; no label or threshold grid','side':'larger score; long tie','cooldown_seconds':600,'comparison':'same architecture and rules; each model may select different times, so no isolated causal attribution','warmup':'21 previous contiguous bars, common finite volume features; no hour-long feature','no_clock_features':True,'Nov2':'not evaluated or fitted in this experiment','Nov3':'not loaded','adoption':'no adoption from consumed five-day test; small samples below50 explicitly inconclusive','status':'RESEARCH_ONLY_NOT_READY'}
 blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(sys.argv[1],'SPX_1min_sample.csv')),'prior20');es=readzip(sys.argv[2],'ES_1min_sample.csv');v=volume_features(es);j=d[['ts']].merge(v,on='ts',how='left',validate='one_to_one');pf=price_features(d);vf=j.drop(columns='ts');allf=pd.concat([pf,vf],axis=1);valid=np.isfinite(allf.values).all(1);calstart=pd.Timestamp('2026-10-22',tz='UTC');teststart=pd.Timestamp('2026-10-26',tz='UTC');lab=ev.label(d,'close');train=valid&(lab['status']==0)&(d.ts<calstart).values;cal=valid&(d.ts>=calstart).values&(d.ts<teststart).values;test=valid&(d.ts>=teststart).values
 for cut in [500,2000,3500]:
  np.testing.assert_allclose(price_features(d.iloc[:cut]),pf.iloc[:cut],equal_nan=True);np.testing.assert_allclose(volume_features(es.iloc[:cut]).drop(columns='ts'),v.iloc[:cut].drop(columns='ts'),equal_nan=True)
 probs={};lock={};fold={'fit_rows':int(train.sum()),'cal_rows':int(cal.sum()),'later_rows':int(test.sum()),'sklearn':sklearn.__version__}
 for name,ff in [('price_only',pf),('price_ES_volume',allf)]:
  X=ff.values;p=np.full((len(d),2),np.nan)
  for k,target in enumerate(['up_c','dn_c']):
   clf=HistGradientBoostingClassifier(**cfg['classifier']).fit(X[train],lab[target][train].astype(int));p[valid,k]=clf.predict_proba(X[valid])[:,1]
  th=float(np.quantile(p[cal].max(axis=1),.98));lock[name]={'threshold':th,'features':list(ff.columns)};probs[name]=p
 calibration=json.dumps({'fold':fold,'models':lock},indent=2);(P/'CALIBRATION_LOCK.json').write_text(calibration);(P/'CALIBRATION_LOCK.sha256').write_text(hashlib.sha256(calibration.encode()).hexdigest())
 rows=[];signals=[]
 for name,p in probs.items():
  ids,side=select(d,p,lock[name]['threshold'],test)
  for entry in ['close','next_open']:r=evaluate(d,ids,side,entry);r['model']=name;rows.append(r)
  for i,dr in zip(ids,side):signals.append({'model':name,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':int(dr),'long_score_uncalibrated':float(p[i,0]),'short_score_uncalibrated':float(p[i,1])})
 out={'fold':fold,'lock':lock,'prefix_checks':6,'rows':rows,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));pd.DataFrame(signals).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
