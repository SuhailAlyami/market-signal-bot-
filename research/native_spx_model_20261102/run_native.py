import hashlib,importlib.util,json
from pathlib import Path
import numpy as np,pandas as pd,sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
P=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('ev',P/'evaluate_previous_models.py');ev=importlib.util.module_from_spec(s);s.loader.exec_module(ev)
def features(d):
 f=pd.DataFrame(index=d.index);a=d.atr
 for k in [1,3,5,15]:f['return'+str(k)+'_ATR']=(d.close-d.close.shift(k))/a
 f['range_ATR']=(d.high-d.low)/a;f['body_ATR']=(d.close-d.open)/a;f['close_position']=((d.close-d.low)/(d.high-d.low).replace(0,np.nan)).fillna(.5)
 ema=d.close.groupby(d.seg).transform(lambda x:x.ewm(span=20,adjust=False).mean());f['EMA20distance_ATR']=(d.close-ema)/a
 pc=d.close.groupby(d.seg).shift(1);tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
 prior60=tr.groupby(d.seg).transform(lambda x:x.shift(1).rolling(60).mean());f['ATR20_to_prior60TR']=a/prior60
 f.loc[d.pos<30,:]=np.nan;return f.replace([np.inf,-np.inf],np.nan)
def select(d,prob,threshold,mask):
 idx=[];side=[];last=None
 for i in np.flatnonzero(mask):
  if not np.isfinite(prob[i]).all() or max(prob[i])<threshold:continue
  now=d.ts.iloc[i].timestamp()
  if last is None or now-last>=600:idx.append(i);side.append(1 if prob[i,0]>=prob[i,1] else -1);last=now
 return np.array(idx,int),np.array(side,int)
def main():
 raw=(P/'DESIGN.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==(P/'DESIGN.sha256').read_text().strip();c=json.loads(raw);out=P/'results';out.mkdir(exist_ok=True)
 rawd,info=ev.EV.load(P/'SPX_1m.csv');d=ev.EV.add_atr(ev.EV.add_structure(rawd),'prior20');f=features(d);X=f.values;valid=np.isfinite(X).all(1);lab=ev.EV.label(d,'close');scorable=lab['status']==0;idx=np.arange(len(d))
 startcal=int(np.flatnonzero(d.ts>=pd.Timestamp('2026-10-28',tz='UTC'))[0]);starttest=int(np.flatnonzero(d.ts>=pd.Timestamp('2026-10-29',tz='UTC'))[0]);train=valid&scorable&(idx+5<startcal);cal=(idx>=startcal)&(idx+5<starttest);test=idx>=starttest
 for cut in [700,1400]:assert np.allclose(features(d.iloc[:cut]).values,f.iloc[:cut].values,equal_nan=True)
 probs=np.full((len(d),2),np.nan)
 for k,target in enumerate(['up_c','dn_c']):
  clf=HistGradientBoostingClassifier(**c['classifier']);clf.fit(X[train],lab[target][train].astype(int));probs[valid,k]=clf.predict_proba(X[valid])[:,1]
 choices=[]
 for th in c['threshold_grid']:
  ii,dd=select(d,probs,th,cal);ok=scorable[ii];ii,dd=ii[ok],dd[ok];n=len(ii);hit=np.where(dd>0,lab['up_c'][ii],lab['dn_c'][ii]);rate=float(hit.mean()) if n else None;p=float((dd>0).mean()) if n else 0;base=float((p*lab['up_c'][ii]+(1-p)*lab['dn_c'][ii]).mean()) if n else None;lo=ev.EV.wilson(int(hit.sum()),n)[0] if n else -1
  choices.append({'threshold':th,'n':n,'hits':int(hit.sum()),'precision':rate,'matched_direction_base':base,'wilson_lower':lo,'eligible':bool(n>=15 and rate>base)})
 eligible=[x for x in choices if x['eligible']];chosen=max(eligible,key=lambda x:(x['wilson_lower'],x['threshold'])) if eligible else None
 lock={'chosen':chosen,'candidates':choices,'train_rows':int(train.sum()),'finite_calibration_rows':int((cal&valid).sum()),'sklearn':sklearn.__version__,'prefix_checks':2};txt=json.dumps(lock,indent=2);(out/'CALIBRATION_LOCK.json').write_text(txt);(out/'CALIBRATION_LOCK.sha256').write_text(hashlib.sha256(txt.encode()).hexdigest());print(txt,flush=True)
 if chosen is None:
  (out/'RESULT.json').write_text(json.dumps({'status':'ABSTAIN_NO_CALIBRATION_CANDIDATE','later_evaluated':False}));return
 ii,dd=select(d,probs,chosen['threshold'],test);dates=d.ts.dt.floor('D').values.astype('datetime64[D]');rows=[]
 for entry in ['close','next_open']:
  l=ev.EV.label(d,entry);r=ev.score_set(ii,dd,l,dates,test,'NATIVE_SPX|'+entry);r.update(entry=entry);rows.append(r)
 pd.DataFrame(rows).to_csv(out/'later_results.csv',index=False);pd.DataFrame({'bar_index':ii,'bar_timestamp':d.ts.iloc[ii].astype(str).values,'direction':dd,'score_long':probs[ii,0],'score_short':probs[ii,1]}).to_csv(out/'later_signals.csv',index=False)
 print(pd.DataFrame(rows)[['entry','n_scored','hits','precision','dir_perm_mean','p_dir','events_detected']].to_string(index=False))
if __name__=='__main__':main()
