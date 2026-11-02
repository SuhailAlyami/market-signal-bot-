"""Two-stage timing/direction diagnostic. Exploratory only."""
import io,sys,json,hashlib,zipfile
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def features(d):
 pc=d.groupby('seg').close.shift(1);tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
 f=pd.DataFrame(index=d.index)
 for n in [1,5,15]:f['return'+str(n)]=(d.close-d.groupby('seg').close.shift(n))/d.atr
 f['range']=(d.high-d.low)/d.atr;f['body']=(d.close-d.open)/d.atr
 f['atr_ratio']=d.atr/tr.groupby(d.seg).transform(lambda s:s.shift(1).rolling(60).mean())
 minute=d.ts.dt.tz_convert('America/New_York').dt.hour*60+d.ts.dt.tz_convert('America/New_York').dt.minute-570
 f['session_sin']=np.sin(2*np.pi*minute/390);f['session_cos']=np.cos(2*np.pi*minute/390)
 f.loc[d.pos<60,:]=np.nan
 return f.replace([np.inf,-np.inf],np.nan)

def main():
 c={'fit':'2026-10-15..2026-10-23','later':'2026-10-26..2026-10-30','timing_label':'either direction reaches 2 prior20ATR within 5 contiguous minutes, ignoring stop','direction_training':'only rows where exactly one direction satisfies 2ATR-before-1ATR success; target long versus short','models':'two StandardScaler + LogisticRegression(C=1,max_iter=1000,random_state=42); no class balancing','threshold':'90th percentile timing training scores, fixed beforehand; no test ranking','cooldown_seconds':600,'features':['return1','return5','return15','range','body','atr_ratio','session_sin','session_cos'],'evaluation':'unchanged close/nextopen 2ATR before1ATR in5minutes; timing success reported separately','limitations':['all dates previously used; exploratory only','small12-session sample','timing and direction are different tasks','model scores not calibrated confidence'],'status':'RESEARCH_ONLY / NOT_READY'}
 b=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 keep=np.zeros(len(d),bool)
 for _,r in xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'].iterrows():keep|=((d.ts>=r.open)&(d.ts<r.close)).values
 d=ev.add_atr(ev.add_structure(d.loc[keep].reset_index(drop=True)),'prior20');f=features(d);X=f.values;valid=np.isfinite(X).all(1);lab=ev.label(d,'close');sc=lab['status']==0
 for cut in [500,2000,3500]:assert np.allclose(features(d.iloc[:cut]).values,X[:cut],equal_nan=True)
 timing=np.zeros(len(d),bool)
 for i in np.flatnonzero(sc):
  fut=d.iloc[i+1:i+6];e=d.close.iloc[i];a=d.atr.iloc[i];timing[i]=fut.high.max()>=e+2*a or fut.low.min()<=e-2*a
 cutoff=pd.Timestamp('2026-10-26',tz='UTC');train=valid&sc&(d.ts<cutoff).values;later=valid&(d.ts>=cutoff).values
 directional=train&(lab['up_c']^lab['dn_c'])
 def model():return make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000,random_state=42))
 tm=model().fit(X[train],timing[train]);dm=model().fit(X[directional],lab['up_c'][directional]);tp=np.full(len(d),np.nan);dp=tp.copy();tp[valid]=tm.predict_proba(X[valid])[:,1];dp[valid]=dm.predict_proba(X[valid])[:,1]
 threshold=float(np.quantile(tp[train],.9));lock={'threshold':threshold,'fit_rows':int(train.sum()),'direction_fit_rows':int(directional.sum()),'train_timing_rate':float(timing[train].mean()),'protocol_sha256':hashlib.sha256(b).hexdigest()};(P/'TRAIN_LOCK.json').write_text(json.dumps(lock,indent=2))
 ids=[];last=None
 for i in np.flatnonzero(later&(tp>=threshold)):
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:ids.append(i);last=now
 ids=np.array(ids,int);rows=[]
 for entry in ['close','next_open']:
  l=ev.label(d,entry);ix=ids[l['status'][ids]==0];dr=np.where(dp[ix]>=.5,1,-1);hit=np.where(dr>0,l['up_c'][ix],l['dn_c'][ix]);p=float((dr>0).mean()) if len(ix) else 0
  base=float((p*l['up_c'][ix]+(1-p)*l['dn_c'][ix]).mean()) if len(ix) else None
  rng=np.random.default_rng(20261102);null=[]
  for _ in range(10000):
   perm=rng.permutation(dr);null.append(float(np.where(perm>0,l['up_c'][ix],l['dn_c'][ix]).mean()) if len(ix) else 0)
  day=d.ts.iloc[ix].dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d').values;daily=[]
  for date in sorted(set(day)):
   m=day==date;daily.append({'date':date,'n':int(m.sum()),'hits':int(hit[m].sum()),'null_expected_hits':float((p*l['up_c'][ix[m]]+(1-p)*l['dn_c'][ix[m]]).sum())})
  diffs=[]
  if daily:
   for _ in range(10000):
    sample=[daily[j] for j in rng.integers(0,len(daily),len(daily))];diffs.append(sum(x['hits']-x['null_expected_hits'] for x in sample)/sum(x['n'] for x in sample))
  rows.append({'entry':entry,'signals':len(ids),'scored':len(ix),'hits':int(hit.sum()),'precision':float(hit.mean()) if len(ix) else None,'same_times_random_direction':base,'direction_permutation_p_exploratory':float((1+sum(x>=hit.mean() for x in null))/10001) if len(ix) else None,'daily':daily,'daily_bootstrap_difference_95_exploratory':np.quantile(diffs,[.025,.975]).tolist() if diffs else None,'warning':'five day blocks only; many prior research attempts; unadjusted exploratory p'})
 ix=ids[sc[ids]];alltest=later&sc
 out={'lock':lock,'prefix_checks':3,'later_rows':int(alltest.sum()),'later_timing_base':float(timing[alltest].mean()),'selected_timing_hits':int(timing[ix].sum()),'selected_timing_count':len(ix),'selected_timing_rate':float(timing[ix].mean()) if len(ix) else None,'direction_results':rows}
 (P/'results.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
 pd.DataFrame({'decision_time_Riyadh':(d.ts.iloc[ids]+pd.Timedelta(minutes=1)).dt.tz_convert('Asia/Riyadh').astype(str).values,'direction':np.where(dp[ids]>=.5,1,-1),'timing_score_uncalibrated':tp[ids]}).to_csv(P/'signals_derived.csv',index=False)
if __name__=='__main__':main()
