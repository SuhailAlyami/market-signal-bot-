"""One ablation: remove clock features from direction only; timing frozen."""
import io,json,hashlib,sys,zipfile
from pathlib import Path
import pandas as pd,numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import early_move_eval_openfix as ev
from features import features
P=Path(__file__).resolve().parent

def main():
 old=json.loads((P.parent/'frozen_replay/MODEL.json').read_text());c={'hypothesis':'Retrain direction logistic on six price features; remove session_sin/cos only from direction; frozen timing model, threshold and cooldown unchanged','motivation':'posthoc Nov2 failed UP signals flipped by clock contributions','training':'Oct15..23 only; excludes Nov2','comparison':'Oct26..30 consumed exploratory data; fixed original timing signals','Nov2':'diagnostic development only; no independent validation claim','future_holdout':'Nov3 onward not loaded','model':'StandardScaler LogisticRegression C1 maxiter1000 random_state42, no tuning','target':'2prior20ATR before1ATR in5contiguous minutes, close and nextopen','status':'NOT_READY_RESEARCH_ONLY'};blob=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC');local=d.ts.dt.tz_convert('America/New_York');minute=local.dt.hour*60+local.dt.minute;d=d[(minute>=570)&(minute<960)&(local.dt.dayofweek<5)].reset_index(drop=True);d=ev.add_atr(ev.add_structure(d),'prior20');f=features(d);X=f.values;valid=np.isfinite(X).all(1);lab=ev.label(d,'close');train=valid&(lab['status']==0)&(d.ts<pd.Timestamp('2026-10-26',tz='UTC')).values;train&=lab['up_c']^lab['dn_c']
 clf=make_pipeline(StandardScaler(),LogisticRegression(C=1,max_iter=1000,random_state=42)).fit(X[train,:6],lab['up_c'][train]);new=clf.predict_proba(X[valid,:6])[:,1];newall=np.full(len(d),np.nan);newall[valid]=new
 ss=clf[0];lr=clf[1];outmodel=json.loads(json.dumps(old));outmodel['models']['direction']={'mean':ss.mean_.tolist()+[0.,0.],'scale':ss.scale_.tolist()+[1.,1.],'coefficient':lr.coef_[0].tolist()+[0.,0.],'intercept':float(lr.intercept_[0])};outmodel['variant']='direction_price_only_clock_removed';outmodel['status']='RESEARCH_ONLY_NOT_READY';(P/'MODEL.json').write_text(json.dumps(outmodel,indent=2))
 m=outmodel['models']['direction'];zv=((X[valid]-np.array(m['mean']))/np.array(m['scale']))@np.array(m['coefficient'])+m['intercept'];assert np.max(np.abs(1/(1+np.exp(-zv))-new))<1e-12
 source=pd.read_csv(P.parent/'timing_research/signals_derived.csv');lookup={str(t+pd.Timedelta(minutes=1)):i for i,t in enumerate(d.ts)};ids=np.array([lookup[str(pd.Timestamp(t).tz_convert('UTC'))] for t in source.decision_time_Riyadh]);oldside=source.direction.values;newside=np.where(newall[ids]>=.5,1,-1);rows=[]
 for entry in ['close','next_open']:
  l=ev.label(d,entry);ok=l['status'][ids]==0;ix=ids[ok];a=oldside[ok];b=newside[ok];ah=np.where(a>0,l['up_c'][ix],l['dn_c'][ix]);bh=np.where(b>0,l['up_c'][ix],l['dn_c'][ix]);p=(b>0).mean();rows.append({'entry':entry,'n':len(ix),'original_hits':int(ah.sum()),'price_only_hits':int(bh.sum()),'original_precision':float(ah.mean()),'price_only_precision':float(bh.mean()),'changed_directions':int((a!=b).sum()),'changes_failure_to_success':int(((~ah)&bh).sum()),'changes_success_to_failure':int((ah&(~bh)).sum()),'new_direction_matched_base':float((p*l['up_c'][ix]+(1-p)*l['dn_c'][ix]).mean())})
 out={'fit_rows':int(train.sum()),'timing_model_changed':False,'timing_threshold_changed':False,'signal_times_changed':False,'export_prediction_check':True,'results':rows,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
