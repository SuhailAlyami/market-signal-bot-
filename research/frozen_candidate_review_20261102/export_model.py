"""Export the exact fixed candidate for subsequent replay, without refitting on later rows."""
import io,json,zipfile,sys,hashlib
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from candidate import features
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def predict(model,X):
 x=(np.asarray(X)-np.array(model['mean']))/np.array(model['scale']);z=x@np.array(model['coefficient'])+model['intercept'];return 1/(1+np.exp(-z))

def main():
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC');keep=np.zeros(len(d),bool)
 for _,r in xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'].iterrows():keep|=((d.ts>=r.open)&(d.ts<r.close)).values
 d=ev.add_atr(ev.add_structure(d.loc[keep].reset_index(drop=True)),'prior20');f=features(d);X=f.values;valid=np.isfinite(X).all(1);lab=ev.label(d,'close');sc=lab['status']==0;timing=np.zeros(len(d),bool)
 for i in np.flatnonzero(sc):
  future=d.iloc[i+1:i+6];e=d.close.iloc[i];a=d.atr.iloc[i];timing[i]=future.high.max()>=e+2*a or future.low.min()<=e-2*a
 train=valid&sc&(d.ts<pd.Timestamp('2026-10-26',tz='UTC')).values;direction=train&(lab['up_c']^lab['dn_c']);out={'status':'RESEARCH_ONLY_NOT_READY','feature_order':list(f.columns),'input_sha256':hashlib.sha256(Path(sys.argv[1]).read_bytes()).hexdigest(),'training_end_date':'2026-10-23','cooldown_seconds':600,'models':{}};checks=[]
 for name,mask,y in [('timing',train,timing),('direction',direction,lab['up_c'])]:
  m=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000,random_state=42)).fit(X[mask],y[mask]);ss=m[0];lr=m[1];j={'mean':ss.mean_.tolist(),'scale':ss.scale_.tolist(),'coefficient':lr.coef_[0].tolist(),'intercept':float(lr.intercept_[0])};out['models'][name]=j
  error=float(np.max(np.abs(predict(j,X[valid])-m.predict_proba(X[valid])[:,1])));assert error<1e-12;checks.append({'model':name,'max_export_probability_error':error})
  if name=='timing':out['timing_threshold']=float(np.quantile(m.predict_proba(X[train])[:,1],.9))
 scores=predict(out['models']['timing'],X[valid]);assert np.isfinite(scores).all()
 (P/'MODEL.json').write_text(json.dumps(out,indent=2));(P/'export_checks.json').write_text(json.dumps(checks,indent=2));print(json.dumps(checks,indent=2))
if __name__=='__main__':main()
