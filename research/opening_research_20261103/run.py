"""Separate first-hour candidate. No Nov2 optimization/evaluation."""
import json,hashlib,io,zipfile,sys
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def features(d):
 f=pd.DataFrame(index=d.index)
 for n in [1,5,15]:f['return'+str(n)]=(d.close-d.groupby('seg').close.shift(n))/d.atr
 f['range']=(d.high-d.low)/d.atr;f['body']=(d.close-d.open)/d.atr
 local=d.ts.dt.tz_convert('America/New_York');minute=local.dt.hour*60+local.dt.minute-570
 f['session_sin']=np.sin(2*np.pi*minute/390);f['session_cos']=np.cos(2*np.pi*minute/390)
 f.loc[(d.pos<21)|(minute>=60)|(minute<0),:]=np.nan
 return f.replace([np.inf,-np.inf],np.nan)

def main():
 protocol={'model':'Separate first-hour two-stage logistic, same C1/maxiter1000/seed42; no class balance','fit':'15..23 Oct2026','exploratory_later':'26..30 Oct2026 consumed data','Nov2':'not fit, not used for threshold, not evaluated for this candidate; motivates hypothesis only','future':'Nov3 onwards not opened','features':['return1','return5','return15','range','body','session_sin','session_cos'],'decision_window':'21 <= contiguous segment position <60 AND wall-clock first60 minutes of regular session; no ATR60 feature','threshold':'90th percentile timing training score; fixed, no threshold grid','cooldown_seconds':600,'timing_label':'touch2ATR either direction ignoring stop in next5 contiguous minutes','direction_label':'long vs short only where exactly one2ATR-before1ATR succeeds','evaluation':'2 prior20SMA TR target before1ATR stop in5min; close primary nextopen secondary; unchanged','acceptance':'no live adoption from consumed5day test; below30scored signals inconclusive; below70precision fails objective regardless','status':'RESEARCH_ONLY_NOT_READY'}
 b=json.dumps(protocol,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC');inside=np.zeros(len(d),bool)
 for _,r in xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'].iterrows():inside|=((d.ts>=r.open)&(d.ts<r.close)).values
 d=ev.add_atr(ev.add_structure(d.loc[inside].reset_index(drop=True)),'prior20');f=features(d);X=f.values;valid=np.isfinite(X).all(1)&(d.pos<60).values;lab=ev.label(d,'close');sc=lab['status']==0;timing=np.zeros(len(d),bool)
 for i in np.flatnonzero(sc):
  future=d.iloc[i+1:i+6];e=d.close.iloc[i];a=d.atr.iloc[i];timing[i]=future.high.max()>=e+2*a or future.low.min()<=e-2*a
 train=valid&sc&(d.ts<pd.Timestamp('2026-10-26',tz='UTC')).values;later=valid&(d.ts>=pd.Timestamp('2026-10-26',tz='UTC')).values;direction=train&(lab['up_c']^lab['dn_c']);models={};prob={}
 for name,m,y in [('timing',train,timing),('direction',direction,lab['up_c'])]:
  clf=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000,random_state=42)).fit(X[m],y[m]);p=np.full(len(d),np.nan);p[valid]=clf.predict_proba(X[valid])[:,1];prob[name]=p;s=clf[0];lr=clf[1];models[name]={'mean':s.mean_.tolist(),'scale':s.scale_.tolist(),'coefficient':lr.coef_[0].tolist(),'intercept':float(lr.intercept_[0])}
 threshold=float(np.quantile(prob['timing'][train],.9));lock={'train_rows':int(train.sum()),'direction_train_rows':int(direction.sum()),'threshold':threshold};(P/'TRAIN_LOCK.json').write_text(json.dumps(lock,indent=2));(P/'MODEL.json').write_text(json.dumps({'models':models,'feature_order':list(f.columns),'timing_threshold':threshold,'status':'RESEARCH_ONLY_NOT_READY','decision_pos_min':21,'decision_pos_max_exclusive':60},indent=2))
 for cut in [500,2000,3500]:np.testing.assert_allclose(features(d.iloc[:cut]).values,X[:cut],equal_nan=True)
 ids=[];last=None
 for i in np.flatnonzero(later&(prob['timing']>=threshold)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);last=now
 ids=np.array(ids,int);side=np.where(prob['direction'][ids]>=.5,1,-1);rows=[]
 for entry in ['close','next_open']:
  l=ev.label(d,entry);ok=l['status'][ids]==0;ix=ids[ok];dr=side[ok];hit=np.where(dr>0,l['up_c'][ix],l['dn_c'][ix]);p=float((dr>0).mean()) if len(ix) else 0;base=float((p*l['up_c'][ix]+(1-p)*l['dn_c'][ix]).mean()) if len(ix) else None;rows.append({'entry':entry,'scored':len(ix),'hits':int(hit.sum()),'precision':float(hit.mean()) if len(ix) else None,'matched_direction_base':base})
 out={'training':lock,'later_eligible_rows':int(later.sum()),'prefix_checks':3,'result':rows,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));pd.DataFrame({'decision_Riyadh':(d.ts.iloc[ids]+pd.Timedelta(minutes=1)).dt.tz_convert('Asia/Riyadh').astype(str).values,'direction':side}).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(out,indent=2))
if __name__=='__main__':main()
