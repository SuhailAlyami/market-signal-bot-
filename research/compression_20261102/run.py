"""Fixed compression-to-small-break experiment. Research only."""
import io,json,hashlib,zipfile,sys
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def detect(d):
 pc=d.groupby('seg').close.shift(1)
 tr=pd.concat([d.high-d.low,(d.high-pc).abs(),(d.low-pc).abs()],axis=1).max(axis=1)
 prior10=tr.groupby(d.seg).transform(lambda s:s.shift(1).rolling(10).mean())
 prior60=tr.groupby(d.seg).transform(lambda s:s.shift(1).rolling(60).mean())
 hi=d.high.groupby(d.seg).transform(lambda s:s.shift(1).rolling(10).max());lo=d.low.groupby(d.seg).transform(lambda s:s.shift(1).rolling(10).min())
 diff=d.groupby('seg').close.diff();path=diff.abs().groupby(d.seg).transform(lambda s:s.rolling(5).sum())
 delta=d.close-d.groupby('seg').close.shift(5);eff=delta.abs()/path.replace(0,np.nan)
 ready=(d.pos>=60)&(prior10<=.75*prior60)&(eff>=.7)&((d.high-d.low)<=1.2*d.atr)&(d.atr>0)
 up=ready&(d.close>hi)&(delta>0);dn=ready&(d.close<lo)&(delta<0)
 return np.where(up,1,np.where(dn,-1,0))

def reason(d,i,side,entry):
 e=d.close.iloc[i] if entry=='close' else d.open.iloc[i+1];a=d.atr.iloc[i]
 for k in range(1,6):
  b=d.iloc[i+k];op=side*(b.open-e)/a
  if op>=2:return 'target'
  if op<=-1:return 'stop'
  favorable=(b.high-e)/a if side==1 else (e-b.low)/a
  adverse=(e-b.low)/a if side==1 else (b.high-e)/a
  if favorable>=2 and adverse>=1:return 'ambiguous'
  if favorable>=2:return 'target'
  if adverse>=1:return 'stop'
 return 'timeout'

def main():
 protocol={'hypothesis':'prior10 mean TR <= .75 prior60 mean TR; 5-bar efficiency >= .7; close outside previous10-bar extremes in 5-bar return direction; decision range <=1.2 prior20ATR','cooldown_seconds':600,'development':'2026-10-15..2026-10-23','later':'2026-10-26..2026-10-30','optimization':'none; no alternate thresholds','target':2,'stop':1,'ATR':'SMA true range prior20 excluding decision','horizon':5,'entry':['close','next_open'],'limitations':['all sample dates previously consumed; exploratory temporal split only','source-native SPX index not CFD','no options PnL evaluated'],'status':'RESEARCH_ONLY / NOT_READY'}
 blob=json.dumps(protocol,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 mask=np.zeros(len(d),bool)
 for _,r in xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'].iterrows():mask|=((d.ts>=r.open)&(d.ts<r.close)).values
 d=ev.add_atr(ev.add_structure(d.loc[mask].reset_index(drop=True)),'prior20');side=detect(d)
 for cut in [500,2000,3500]:assert np.array_equal(detect(d.iloc[:cut]),side[:cut])
 dates=d.ts.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');rows=[];signals=[]
 for period,mask in [('development',dates<'2026-10-26'),('later',dates>='2026-10-26')]:
  ids=[];last=None
  for i in np.flatnonzero(mask.values&(side!=0)):
   now=d.ts.iloc[i].timestamp()
   if last is None or now-last>=600:ids.append(i);last=now
  ids=np.array(ids,int)
  for entry in ['close','next_open']:
   lab=ev.label(d,entry);ix=ids[lab['status'][ids]==0];dr=side[ix];hits=np.where(dr>0,lab['up_c'][ix],lab['dn_c'][ix]);n=len(ix);p=float((dr>0).mean()) if n else 0
   reasons=[reason(d,i,int(side[i]),entry) for i in ix];assert sum(x=='target' for x in reasons)==int(hits.sum())
   counts={r:reasons.count(r) for r in ['target','stop','ambiguous','timeout']}
   base=float((p*lab['up_c'][ix]+(1-p)*lab['dn_c'][ix]).mean()) if n else None
   either=lab['up_c'][ix]|lab['dn_c'][ix]
   touched=[]
   for i in ix:
    price=d.close.iloc[i] if entry=='close' else d.open.iloc[i+1]
    future=d.iloc[i+1:i+6];a=d.atr.iloc[i]
    touched.append(bool(future.high.max()>=price+2*a or future.low.min()<=price-2*a))
   row={'period':period,'entry':entry,'signals':len(ids),'scored':n,'hits':int(hits.sum()),'precision':float(hits.mean()) if n else None,'same_times_random_direction':base,'outcomes':counts,'posthoc_diagnostic_only':{'either_direction_could_succeed':int(either.sum()),'either_direction_target_touched_ignoring_stop':sum(touched),'warning':'future-based explanatory upper bound; never a live feature'}};rows.append(row)
   for i,r in zip(ix,reasons):signals.append({'period':period,'entry':entry,'decision_time_Riyadh':str(d.ts.iloc[i].tz_convert('Asia/Riyadh')+pd.Timedelta(minutes=1)),'direction':int(side[i]),'outcome':r})
 (P/'results.json').write_text(json.dumps({'prefix_checks':3,'rows':rows},indent=2));pd.DataFrame(signals).to_csv(P/'signals_derived.csv',index=False);print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
