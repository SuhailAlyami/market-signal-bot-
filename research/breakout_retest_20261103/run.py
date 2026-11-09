"""Fixed causal 20-minute breakout/retest research, no optimization."""
import json,hashlib
from pathlib import Path
import numpy as np
from data_io import readzip
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def detect(d):
 out=np.zeros(len(d),int);pending=None
 for i in range(len(d)):
  c=d.iloc[i]
  if c.pos<21 or not np.isfinite(c.atr) or c.atr<=0:pending=None;continue
  if pending:
   j,side,level,a,seg=pending
   if c.seg!=seg or i-j>5 or (side==1 and c.close<level-.2*a) or (side==-1 and c.close>level+.2*a):pending=None
   elif i>j:
    yes=(c.low<=level+.2*a and c.low>=level-.2*a and c.close>level and c.close>c.open) if side==1 else (c.high>=level-.2*a and c.high<=level+.2*a and c.close<level and c.close<c.open)
    if yes:out[i]=side;pending=None;continue
  if pending is None:
   w=d.iloc[i-20:i];hi=w.high.max();lo=w.low.min()
   if c.close>hi+.1*c.atr:pending=(i,1,float(hi),float(c.atr),c.seg)
   elif c.close<lo-.1*c.atr:pending=(i,-1,float(lo),float(c.atr),c.seg)
 return out

def main():
 protocol={'rule':'close breaks previous20 highs/lows by0.1 priorATR; within next1..5 bars retest level +/-0.2 breakoutATR, directional body and close beyond level; cancel close through opposite edge, gap or expiry; decision at retest close','target':2,'stop':1,'horizon_minutes':5,'ATR':'prior20 SMA true range','cooldown_seconds':600,'parameters':'fixed before run, no tuning','sample':'12 consumed Oct15..30 sessions, earlier7/later5 descriptive only','status':'NOT_READY'}
 b=json.dumps(protocol,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');s=detect(d)
 for cut in [500,2000,3500]:assert np.array_equal(detect(d.iloc[:cut]),s[:cut])
 dates=d.ts.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');rows=[]
 for name,m in [('earlier',dates<'2026-10-26'),('later',dates>='2026-10-26')]:
  ids=[];last=None
  for i in np.flatnonzero(m.values&(s!=0)):
   t=d.ts.iloc[i].timestamp()
   if last is None or t-last>=600:ids.append(i);last=t
  ids=np.array(ids,int)
  for entry in ['close','next_open']:
   lab=ev.label(d,entry);idx=ids[lab['status'][ids]==0];dr=s[idx];n=len(idx);up=lab['up_c'][idx];dn=lab['dn_c'][idx];hit=np.where(dr>0,up,dn);p=float((dr>0).mean()) if n else 0
   rows.append({'period':name,'entry':entry,'signals':len(ids),'scored':n,'hits':int(hit.sum()),'precision':float(hit.mean()) if n else None,'same_time_direction_shuffle_expected':float((p*up+(1-p)*dn).mean()) if n else None})
 result={'rows':rows,'prefix_checks':3,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
