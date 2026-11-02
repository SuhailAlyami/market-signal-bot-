"""Frozen two-bar failed-range-break replication. No parameter optimization."""
import io,json,hashlib,zipfile,sys
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def detect(d):
 out=np.zeros(len(d),int)
 for i in range(31,len(d)):
  w=d.iloc[i-31:i-1];s=d.iloc[i-1];c=d.iloc[i]
  if c.pos<31 or not np.isfinite(s.atr) or s.atr<=0:continue
  hi=w.high.max();lo=w.low.min();mid=(s.high+s.low)/2
  # Sweep and re-entry at t-1, confirmation at t; no backdating.
  up=s.low<=lo-.1*s.atr and s.close>lo and c.close>s.high and c.close>mid
  dn=s.high>=hi+.1*s.atr and s.close<hi and c.close<s.low and c.close<mid
  if up!=dn:out[i]=1 if up else -1
 return out

def main():
 protocol={'rule':'previous bar sweeps prior30 range by >=0.1 prior20 ATR and closes back inside; current closed bar confirms beyond sweep-bar opposite extreme; decision current close','cooldown_seconds':600,'development_end_exclusive':'2026-10-26','later_start':'2026-10-26','target_ATR':2,'stop_ATR':1,'horizon_minutes':5,'primary_entry':'close','secondary_entry':'next_open','optimization':'none; one fixed hypothesis','limitations':['all dates already consumed in earlier ACCEL replication','not independent holdout','only twelve sessions; later subset five sessions'],'status':'RESEARCH_ONLY / NOT_READY'}
 b=json.dumps(protocol,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 z=zipfile.ZipFile(sys.argv[1]);d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d['ts']=pd.to_datetime(d.pop('timestamp')).dt.tz_localize('America/New_York').dt.tz_convert('UTC')
 sch=xc.get_calendar('XNYS').schedule.loc['2026-10-15':'2026-10-30'];mask=np.zeros(len(d),bool)
 for _,r in sch.iterrows():mask|=((d.ts>=r.open)&(d.ts<r.close)).values
 d=ev.add_atr(ev.add_structure(d.loc[mask].reset_index(drop=True)),'prior20');side=detect(d)
 for cut in [500,2000,3500]:assert np.array_equal(detect(d.iloc[:cut]),side[:cut])
 dates=d.ts.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');rows=[]
 for group,m in [('development',dates<'2026-10-26'),('later',dates>='2026-10-26')]:
  ids=[];last=None
  for i in np.flatnonzero(m.values&(side!=0)):
   now=d.ts.iloc[i].timestamp()
   if last is None or now-last>=600:ids.append(i);last=now
  ids=np.array(ids,int)
  for entry in ['close','next_open']:
   lab=ev.label(d,entry);idx=ids[lab['status'][ids]==0];dr=side[idx];hits=np.where(dr>0,lab['up_c'][idx],lab['dn_c'][idx]);n=len(idx);p=float((dr>0).mean()) if n else 0
   base=float((p*lab['up_c'][idx]+(1-p)*lab['dn_c'][idx]).mean()) if n else None
   mom=np.sign(d.close-d.close.shift(5)).values[idx];mh=np.where(mom>0,lab['up_c'][idx],lab['dn_c'][idx]);usable=mom!=0
   rng=np.random.default_rng(20261102);null=[]
   if n:
    for _ in range(10000):
     perm=rng.permutation(dr);null.append(float(np.where(perm>0,lab['up_c'][idx],lab['dn_c'][idx]).mean()))
   rows.append({'period':group,'entry':entry,'signals':len(ids),'scored':n,'hits':int(hits.sum()),'precision':float(hits.mean()) if n else None,'same_times_random_direction':base,'same_times_momentum_precision':float(mh[usable].mean()) if usable.any() else None,'direction_permutation_p_exploratory':float((1+sum(v>=hits.mean() for v in null))/10001) if n else None,'wilson_independence_descriptive':ev.wilson(int(hits.sum()),n) if n else None})
 (P/'results.json').write_text(json.dumps({'checks':{'prefix_invariance':3},'rows':rows},indent=2));print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
