"""Fixed two-sided cumulative-shift detector. No training or grid search."""
import io,json,zipfile,hashlib,sys
from pathlib import Path
import pandas as pd,numpy as np
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def detect(d):
 side=np.zeros(len(d),int);gp=gn=0.;last_seg=None;last_signal=None
 for i,row in enumerate(d.itertuples()):
  if row.seg!=last_seg:gp=gn=0.;last_seg=row.seg
  if row.pos<21 or not np.isfinite(row.atr) or row.atr<=0:continue
  r=(row.close-d.close.iloc[i-1])/row.atr;gp=max(0.,gp+r-.1);gn=min(0.,gn+r+.1)
  dr=1 if gp>=1.5 else -1 if gn<=-1.5 else 0
  if dr:
   gp=gn=0.
   if last_signal is None or (row.ts-last_signal).total_seconds()>=600:side[i]=dr;last_signal=row.ts
 return side

def load():
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC');loc=d.ts.dt.tz_convert('America/New_York');mins=loc.dt.hour*60+loc.dt.minute;d=d[(mins>=570)&(mins<960)&(loc.dt.dayofweek<5)].reset_index(drop=True)
 return ev.add_atr(ev.add_structure(d),'prior20')

def score(d,side,mask,name):
 ids=np.flatnonzero(mask&(side!=0));rows=[]
 for entry in ['close','next_open']:
  l=ev.label(d,entry);ix=ids[l['status'][ids]==0];dr=side[ix];n=len(ix);hit=np.where(dr>0,l['up_c'][ix],l['dn_c'][ix]);p=float((dr>0).mean()) if n else 0;mom=np.sign(d.close-d.groupby('seg').close.shift(5)).values[ix];mh=np.where(mom>0,l['up_c'][ix],l['dn_c'][ix]);validmom=mom!=0
  rows.append({'period':name,'entry':entry,'signals':len(ids),'scored':n,'hits':int(hit.sum()),'precision':float(hit.mean()) if n else None,'matched_direction_base':float((p*l['up_c'][ix]+(1-p)*l['dn_c'][ix]).mean()) if n else None,'momentum_hits':int(mh[validmom].sum()),'momentum_n':int(validmom.sum()),'first_hour_signals':int((d.pos.iloc[ids]<60).sum())})
 return rows

def main():
 c={'hypothesis':'two-sided cumulative normalized returns after noise subtraction; no candle morphology, clock classifier, or fitting','normalizer':'mean20 prior TR excluding decision bar','update':'gplus=max(0,gplus+return/ATR-.1); gminus=min(0,gminus+return/ATR+.1)','threshold':1.5,'crossing':'positive1.5 long, negative1.5 short; reset BOTH accumulators at every crossing, even during cooldown','cooldown_seconds':600,'warmup':'21 prior contiguous bars; reset accumulators on every gap or session','evaluation':'target2priorATR before1priorATR stop within next5contiguous minutes; close primary,nextopen secondary; ambiguous fails','periods':['Oct15-23 development','Oct26-30 consumed later comparison','Nov2 consumed diagnostic only'],'Nov3':'not loaded; no future outcome used','optimization':'one fixed rule, no parameter grid or after-result retuning','status':'RESEARCH_ONLY_NOT_READY'};b=json.dumps(c,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 d=load();side=detect(d)
 for cut in [500,2000,3500]:assert np.array_equal(detect(d.iloc[:cut]),side[:cut])
 cut=pd.Timestamp('2026-10-26',tz='UTC');rows=score(d,side,(d.ts<cut).values,'development')+score(d,side,(d.ts>=cut).values,'later_consumed')
 n=pd.read_csv(P.parent/'nov2_final_review/SPX_20261102.csv');n['ts']=pd.to_datetime(n.pop('timestamp'),utc=True);n=ev.add_atr(ev.add_structure(n),'prior20');ns=detect(n);rows+=score(n,ns,np.ones(len(n),bool),'Nov2_diagnostic_consumed')
 (P/'RESULT.json').write_text(json.dumps({'rows':rows,'prefix_checks':3,'status':'NOT_READY'},indent=2))
 sig=[]
 for data,ss,source in [(d,side,'FirstRate'),(n,ns,'IBKR')]:
  for i in np.flatnonzero(ss):sig.append({'source':source,'decision_Riyadh':str((data.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':int(ss[i])})
 pd.DataFrame(sig).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
