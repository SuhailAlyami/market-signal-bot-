"""Explicit multi-timeframe adaptation of49-input direction research."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd,exchange_calendars as xc
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P/'engine'))
import features as ft
import early_move_eval_openfix as ev
FRAMES={'FIVE_MINS':5,'FIFTEEN_MINS':15,'THIRTY_MINS':30,'ONE_DAY':None}

def raw(path):
 r=json.loads(path.read_text());d=pd.DataFrame({k:r[k] for k in ['open','high','low','close']});d['ts']=pd.to_datetime(r['time'],utc=True);d['volume']=r.get('volume',np.zeros(len(d)));assert d.ts.is_monotonic_increasing and not d.ts.duplicated().any()
 good=np.isfinite(d[['open','high','low','close']]).all(axis=1)&(d[['open','high','low','close']]>0).all(axis=1)&(d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))
 audit={'raw_rows':len(d),'excluded_OHLC_inconsistent':int((~good).sum()),'excluded_times':d.ts[~good].astype(str).tolist(),'volume_zero_rows':int((d.volume==0).sum()),'note':'No repair or future imputation; excluded bars create expected-grid gaps and reset features.'};(P/(path.stem+'_DATA_AUDIT.json')).write_text(json.dumps(audit,indent=2));return d.loc[good].reset_index(drop=True)

def prepare(sp,es,minutes):
 cal=xc.get_calendar('XNYS',start='2022-01-01',end='2026-12-31');sch=cal.schedule.loc['2022-11-01':'2026-12-31'];slots=[];ends=[];days=[]
 for day,r in sch.iterrows():
  starts=[r.open] if minutes is None else pd.date_range(r.open,r.close-pd.Timedelta(minutes=minutes),freq=f'{minutes}min')
  for t in starts:slots.append(t);ends.append(r.close if minutes is None else t+pd.Timedelta(minutes=minutes));days.append(str(day.date()))
 lookup=pd.DatetimeIndex(slots)
 def align(d):
  d=d.copy()
  if minutes is None:
   # Daily price keyed by NY calendar date; ES daily volume disabled separately.
   mapper={day:i for i,day in enumerate(days)};idx=np.array([mapper.get(str(t.tz_convert('America/New_York').date()),-1) for t in d.ts])
  else:idx=lookup.get_indexer(d.ts)
  mask=idx>=0;d=d.loc[mask].copy();idx=idx[mask];d['slot']=idx;d['source_ts']=d.ts;d['available']=pd.DatetimeIndex(ends).take(idx);d['session']=np.array(days)[idx];d['ts']=pd.Timestamp('2000-01-01',tz='UTC')+pd.to_timedelta(idx,unit='min');d['seg']=(d.slot.diff()!=1).cumsum();d['pos']=d.groupby('seg').cumcount();return d.reset_index(drop=True)
 d=align(sp);es=align(es);d=ev.add_atr(d,'prior20');return d,es

def select(d,eligible):
 ids=[];lastslot=None
 for i in np.flatnonzero(eligible):
  # Shared ten-trading-bar cooldown; explicit scaling, not ten wall minutes.
  slot=int(d.slot.iloc[i])
  if lastslot is None or slot-lastslot>=10:ids.append(i);lastslot=slot
 return np.array(ids,int)

def main():
 cfg={'frames':FRAMES,'adaptation':'Indicator periods measured in bars of chosen timeframe, conventional across closed NYSE sessions; reset on missing expected bars. Original18 generators receive ordinal1min computational clock only, actual timestamps retained for availability/evaluation. No source prices resampled or relabeled as live.','target':'intraday endpoint30 wall minutes on same session:5m6bars,15m2bars,30m1bar; daily next NYSE session close','model':'same fixed StandardScaler LogisticRegression C=.1 max_iter2000 seed42, retrained separately each frame','split':'first60% sessions fit,next20% calibration,last20% evaluation; purge horizon crossing split; cutoff fixed90th percentile calibration event score, labels unused','eligibility':'60prior trading bars, existing18-model event, shared10trading-bar cooldown; no scan or best-frame selection','daily_volume':'disabled:809/975 zero ESvolume and daily session definition not established; price+patterns only, volume model explicitly blocked','minimum':'at least100 fit rows and both classes; else BLOCKED insufficient data','status':'NOT_READY; archival exploratory histories, no independent untouched claim'}
 b=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest());report=[]
 for frame,minutes in FRAMES.items():
  sp=raw(P/'raw'/('SPX_'+frame+'.json'));es=raw(P/'raw'/('ES_'+frame+'.json'));d,ee=prepare(sp,es,minutes);tf=ft.technical(d,ee);pf=ft.patterns(d);allf=pd.concat([tf,pf],axis=1);pricef=allf.drop(columns=['log_rvol','log_rvol_lag1','log_volume5ratio']);candidate=(pf.values!=0).any(1);h=1 if minutes is None else 30//minutes;n=len(d);targetidx=np.arange(n)+h;endok=targetidx<n
  for i in np.flatnonzero(endok):endok[i]=d.seg.iloc[i]==d.seg.iloc[i+h] and (minutes is None or d.session.iloc[i]==d.session.iloc[i+h])
  delta=np.full(n,np.nan);ix=np.flatnonzero(endok);delta[ix]=d.close.iloc[ix+h].values-d.close.iloc[ix].values;y=delta>0;dates=sorted(d.session.unique());a=max(1,int(len(dates)*.6));b=max(a+1,int(len(dates)*.8));b=min(b,len(dates)-1);fitend=dates[a];teststart=dates[b];fitbase=(d.session<fitend).values;calbase=(d.session>=fitend).values&(d.session<teststart).values;testbase=(d.session>=teststart).values
  for name,f in [('price_patterns',pricef),('price_patterns_volume',allf)]:
   base={'frame':frame,'variant':name,'SPX_raw_rows':len(json.loads((P/'raw'/('SPX_'+frame+'.json')).read_text())['time']),'usable_price_bars':len(d),'sessions':len(dates),'fit_end_exclusive':fitend,'test_start':teststart,'target_bars':h,'calendar':'XNYS','feature_count':len(f.columns)}
   if minutes is None and name.endswith('_volume'):report.append(dict(base,status='BLOCKED_DAILY_VOLUME_PROVENANCE'));continue
   valid=np.isfinite(f.values).all(1);train=valid&endok&fitbase&(delta!=0)
   # Purge any label whose endpoint reaches calibration.
   train[ix]=train[ix]&(d.session.iloc[ix+h].values<fitend)
   cal=valid&candidate&calbase;test=valid&candidate&testbase
   if train.sum()<100 or np.unique(y[train]).size<2 or cal.sum()<5:report.append(dict(base,status='BLOCKED_INSUFFICIENT_DATA',fit_rows=int(train.sum()),calibration_events=int(cal.sum())));continue
   clf=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000,random_state=42)).fit(f.values[train],y[train]);p=np.full(n,np.nan);p[valid]=clf.predict_proba(f.values[valid])[:,1];score=np.maximum(p,1-p);side=np.where(p>=.5,1,-1);th=float(np.quantile(score[cal],.9));lock={'features':list(f.columns),'threshold':th,'mean':clf[0].mean_.tolist(),'scale':clf[0].scale_.tolist(),'coefficients':clf[1].coef_[0].tolist(),'intercept':float(clf[1].intercept_[0])};(P/(frame+'_'+name+'_MODEL.json')).write_text(json.dumps(lock,indent=2))
   for policy,mask in [('all_events',test),('selective',test&(score>=th))]:
    ids=select(d,mask);scored=ids[endok[ids]];signed=side[scored]*delta[scored];longshare=float((side[scored]>0).mean()) if len(scored) else 0;dd=delta[scored]
    report.append(dict(base,policy=policy,status='RESEARCH_ONLY_NOT_READY',fit_rows=int(train.sum()),calibration_events=int(cal.sum()),signals=len(ids),scored=len(scored),excluded_incomplete_horizon=len(ids)-len(scored),hits=int((signed>0).sum()),direction_rate=float((signed>0).mean()) if len(scored) else None,mean_signed_points=float(signed.mean()) if len(scored) else None,random_direction_same_times=float((longshare*(dd>0)+(1-longshare)*(dd<0)).mean()) if len(scored) else None))
  # Full-indicator prefix causality with trading-bar computational clock.
  cut=max(100,len(d)//2);np.testing.assert_allclose(ft.technical(d.iloc[:cut],ee),tf.iloc[:cut],equal_nan=True);np.testing.assert_array_equal(ft.patterns(d.iloc[:cut]),pf.iloc[:cut])
 (P/'RESULT.json').write_text(json.dumps({'rows':report,'prefix_checks':8,'status':'NOT_READY'},indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
