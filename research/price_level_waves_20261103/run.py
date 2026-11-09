"""Causal price-level regimes: frozen range and state, not candle-shape prediction."""
import json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
from data_io import readzip
import early_move_eval_openfix as ev
P=Path(__file__).resolve().parent

def detect(d):
 records=[];active=None;candidate=None;lastside=0;segment=None
 for i,c in enumerate(d.itertuples()):
  if segment!=c.seg:
   if active is not None:active.update(end=i-1,end_reason='SESSION_OR_GAP');records.append(active)
   active=None;candidate=None;lastside=0;segment=c.seg
  if c.pos<21 or not np.isfinite(c.atr) or c.atr<=0:continue
  if active is not None:
   # Closing-price structural invalidation. No intrabar stop assumption.
   if active['side']*(c.close-active['invalidation'])<=0:
    active.update(end=i,end_reason='STRUCTURE_BREAK');records.append(active);active=None
   else:continue
  if candidate is not None:
   dr,lo,hi,j=candidate
   holds=c.close>hi if dr==1 else c.close<lo
   if holds and i==j+1:
    if dr!=lastside:
     active={'i':i,'side':dr,'origin':j,'range_low':lo,'range_high':hi,'invalidation':(hi+lo)/2,'entry':float(c.close),'atr':float(c.atr)};lastside=dr
    candidate=None
    if active is not None:continue
   else:candidate=None
  w=d.iloc[i-20:i];lo=float(w.close.min());hi=float(w.close.max())
  dr=1 if c.close>hi else (-1 if c.close<lo else 0)
  if dr!=0 and dr!=lastside:candidate=(dr,lo,hi,i)
 if active is not None:active.update(end=len(d)-1,end_reason='DATA_END');records.append(active)
 return records

def main():
 cfg={'unit':'price-level wave, no candle shape/RSI/volume rules','range':'previous20 CLOSED minute closes; freeze at breakout','confirmation':'two consecutive closes beyond frozen range edge; signal only second close','state':'one active wave until close crosses frozen range midpoint; same direction blocked until opposite confirmed or new segment','evaluation':'future CLOSED prices only until structural break or session end; extension2ATR diagnostic, no five-minute constraint and no old1ATR stop','censoring':'session/gap/end before extension is unresolved, never silently deleted','sample':'12 consumed SPX sessions; chronological earlier7/later5 descriptive only','optimization':'none; first fixed wave protocol','status':'NOT_READY'}
 blob=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');waves=detect(d)
 # Only decision facts compared: future is allowed to set eventual end, never the signal.
 decision=lambda rs:[{k:v for k,v in x.items() if k not in ['end','end_reason']} for x in rs]
 for cut in [500,2000,3500]:assert decision(detect(d.iloc[:cut]))==decision([x for x in waves if x['i']<cut])
 rows=[]
 for w in waves:
  i=w['i'];end=w['end'];future=d.close.iloc[i+1:end+1].to_numpy();progress=w['side']*(future-w['entry']);mfe=max(0.,float(progress.max())) if len(progress) else 0.;mae=max(0.,float(-progress.min())) if len(progress) else 0.;hit=np.flatnonzero(progress>=2*w['atr']);out='EXTENDED_2ATR' if len(hit) else ('STRUCTURE_FAILED' if w['end_reason']=='STRUCTURE_BREAK' else 'UNRESOLVED_SESSION_OR_END')
  rows.append({'period':'earlier' if d.ts.iloc[i]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':w['side'],'entry':w['entry'],'range_low':w['range_low'],'range_high':w['range_high'],'invalidation':w['invalidation'],'outcome':out,'end_reason':w['end_reason'],'duration_minutes':end-i,'max_favorable_points':mfe,'max_adverse_points':mae,'end_displacement_points':float(progress[-1]) if len(progress) else 0.,'minutes_to_2ATR':int(hit[0]+1) if len(hit) else None,'already_moved_from_range_edge_points':w['side']*(w['entry']-(w['range_high'] if w['side']==1 else w['range_low']))})
 pd.DataFrame(rows).to_csv(P/'waves_derived.csv',index=False);summary=[]
 for period in ['earlier','later']:
  rr=[x for x in rows if x['period']==period];n=len(rr);counts={k:sum(x['outcome']==k for x in rr) for k in ['EXTENDED_2ATR','STRUCTURE_FAILED','UNRESOLVED_SESSION_OR_END']}
  summary.append({'period':period,'waves':n,'outcomes':counts,'extended_fraction_all_waves':counts['EXTENDED_2ATR']/n if n else None,'median_favorable_points':float(np.median([x['max_favorable_points'] for x in rr])) if n else None,'median_adverse_points':float(np.median([x['max_adverse_points'] for x in rr])) if n else None,'median_end_displacement_points':float(np.median([x['end_displacement_points'] for x in rr])) if n else None,'median_already_moved_beyond_range':float(np.median([x['already_moved_from_range_edge_points'] for x in rr])) if n else None})
 result={'summary':summary,'prefix_checks':3,'status':'NOT_READY','warning':'New wave metric, not comparable to old2ATR-before1ATR-in5min precision. Extension may later reverse and lose; no profitability claim.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
