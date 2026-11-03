"""Expanding chronological evaluation with fixed model and matched price/volume masks."""
import sys,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'multiframe_unified'))
import run as base

def folds(n):
 for start in range(400,n,100):yield start-100,start,min(start+100,n)

def training_mask(n,h,fitend,common,ok,delta):
 return common&ok&(np.arange(n)+h<fitend)&(delta!=0)

def main():
 cfg={'protocol':'expanding walkforward fixed first300rows fit,next100calibration,next100evaluation; advance100 and expand fit; final short block retained','purge':'training endpoint strictly before calibration index, same segment; intraday target same NYSE session','model':'same C=.1 LogisticRegression StandardScaler, no search','features':'same46price+patterns or49withESvolume; common finite49mask for intraday comparisons, daily price only','threshold':'90th percentile calibration event score, labels unused; compare all/selective without selecting best','cooldown':'10trading bars per variant/policy persists between test folds','sample':'same existing histories, chronologically out-of-fit but not pristine independent evidence after earlier research','status':'NOT_READY'}
 blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest());details=[];audits=[]
 for frame,minutes in base.FRAMES.items():
  d,es=base.prepare(base.raw(base.P/'raw'/('SPX_'+frame+'.json')),base.raw(base.P/'raw'/('ES_'+frame+'.json')),minutes);tf=base.ft.technical(d,es);pf=base.ft.patterns(d);allf=pd.concat([tf,pf],axis=1);price=allf.drop(columns=['log_rvol','log_rvol_lag1','log_volume5ratio']);common=np.isfinite((price if minutes is None else allf).values).all(1);candidate=(pf.values!=0).any(1);n=len(d);h=1 if minutes is None else 30//minutes;delta=np.full(n,np.nan);ok=np.zeros(n,bool)
  for i in range(n-h):
   if d.seg.iloc[i]==d.seg.iloc[i+h] and (minutes is None or d.session.iloc[i]==d.session.iloc[i+h]):ok[i]=True;delta[i]=d.close.iloc[i+h]-d.close.iloc[i]
  for variant,f in [('price',price)]+([] if minutes is None else [('price_volume',allf)]):
   last={'all_events':None,'selective':None}
   for fitend,teststart,testend in folds(n):
    idx=np.arange(n);train=training_mask(n,h,fitend,common,ok,delta);cal=common&candidate&(idx>=fitend)&(idx<teststart);test=common&candidate&(idx>=teststart)&(idx<testend)
    audit={'frame':frame,'variant':variant,'fit_end_index_exclusive':fitend,'test_start_index':teststart,'test_end_index_exclusive':testend,'fit_rows':int(train.sum()),'calibration_events':int(cal.sum())}
    if train.sum()<100 or np.unique(delta[train]>0).size<2 or cal.sum()<5:audits.append(dict(audit,status='INSUFFICIENT'));continue
    clf=make_pipeline(StandardScaler(),LogisticRegression(C=.1,max_iter=2000,random_state=42)).fit(f.values[train],delta[train]>0);valid=common&(idx>=fitend)&(idx<testend);p=np.full(n,np.nan);p[valid]=clf.predict_proba(f.values[valid])[:,1];score=np.maximum(p,1-p);threshold=float(np.quantile(score[cal],.9));dr=np.where(p>=.5,1,-1);lock={'frame':frame,'variant':variant,'test_start':teststart,'fit_end_exclusive':fitend,'features':list(f.columns),'mean':clf[0].mean_.tolist(),'scale':clf[0].scale_.tolist(),'coefficients':clf[1].coef_[0].tolist(),'intercept':float(clf[1].intercept_[0]),'threshold':threshold,'status':'RESEARCH_ONLY_UNCALIBRATED'};(P/'models').mkdir(exist_ok=True);(P/'models'/(frame+'_'+variant+'_'+str(teststart)+'.json')).write_text(json.dumps(lock,indent=2));audits.append(dict(audit,status='EVALUATED',threshold=threshold,test_start_available=str(d.available.iloc[teststart])))
    for policy,mask in [('all_events',test),('selective',test&(score>=threshold))]:
     for i in np.flatnonzero(mask):
      slot=int(d.slot.iloc[i])
      if last[policy] is not None and slot-last[policy]<10:continue
      last[policy]=slot
      details.append({'frame':frame,'variant':variant,'policy':policy,'fold_start':teststart,'decision_Riyadh':str(d.available.iloc[i].tz_convert('Asia/Riyadh')),'side':int(dr[i]),'scorable':bool(ok[i]),'signed_points':float(dr[i]*delta[i]) if ok[i] else None})
 df=pd.DataFrame(details);summary=[]
 for key,g in df.groupby(['frame','variant','policy'],sort=False):
  scored=g[g.scorable];v=scored.signed_points.to_numpy();summary.append({'frame':key[0],'variant':key[1],'policy':key[2],'signals':len(g),'scored':len(scored),'hits':int((v>0).sum()),'rate':float((v>0).mean()) if len(v) else None,'mean_signed_points':float(v.mean()) if len(v) else None,'folds_with_signals':int(g.fold_start.nunique())})
 df.to_csv(P/'signals_derived.csv',index=False);(P/'FOLDS.json').write_text(json.dumps(audits,indent=2));(P/'RESULT.json').write_text(json.dumps({'rows':summary,'status':'NOT_READY'},indent=2));print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
