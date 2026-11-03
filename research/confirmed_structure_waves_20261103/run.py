"""Causal confirmed-pivot structure waves; first fixed specification."""
import json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from data_io import readzip
import early_move_eval_openfix as ev
from reference_legs import legs
P=Path(__file__).resolve().parent

def detect(d):
 waves=[];active=None;highs=[];lows=[];segment=None;used=set()
 for i,c in enumerate(d.itertuples()):
  if c.seg!=segment:
   if active is not None:active.update(end=i-1,end_reason='SESSION_OR_GAP');waves.append(active)
   active=None;highs=[];lows=[];used=set();segment=c.seg
  # Pivot center j is known only after two subsequent CLOSED bars.
  if c.pos>=4:
   j=i-2;v=d.close.iloc[j];window=d.close.iloc[j-2:j+3]
   if v>window.iloc[:2].max() and v>window.iloc[3:].max():highs.append((j,float(v),i))
   if v<window.iloc[:2].min() and v<window.iloc[3:].min():lows.append((j,float(v),i))
  if c.pos<21 or not np.isfinite(c.atr) or c.atr<=0:continue
  if active is not None:
   if active['side']*(c.close-active['invalidation'])<=0:active.update(end=i,end_reason='STRUCTURE_BREAK');waves.append(active);active=None
   else:continue
  candidates=[]
  if highs and len(lows)>=2:
   h=highs[-1];a,b=lows[-2:]
   if a[0]<h[0]<b[0] and b[1]>a[1] and c.close>h[1] and (1,h[0],b[0]) not in used:candidates.append((1,h,b))
  if lows and len(highs)>=2:
   l=lows[-1];a,b=highs[-2:]
   if a[0]<l[0]<b[0] and b[1]<a[1] and c.close<l[1] and (-1,l[0],b[0]) not in used:candidates.append((-1,l,b))
  if len(candidates)==1:
   side,level,pivot=candidates[0];used.add((side,level[0],pivot[0]));active={'i':i,'side':side,'entry':float(c.close),'atr':float(c.atr),'invalidation':pivot[1],'level':level[1],'level_pivot_i':level[0],'invalidation_pivot_i':pivot[0],'last_pivot_confirmed_i':pivot[2]}
 if active is not None:active.update(end=len(d)-1,end_reason='DATA_END');waves.append(active)
 return waves

def main():
 cfg={'rule':'strict close pivot2left2right, recognized only at center+2; long higher-low with intervening confirmed high then close above high, short mirrored; one active wave until frozen last structural pivot broken on close; consumed structure cannot retrigger, fresh structure may','evaluation':'same wave extension2prior20ATR on subsequent closes before structure break/session, no five-minute cap or1ATR stop; retrospective10point reference for coverage only','sample':'12 consumed Oct15..30 sessions earlier7/later5, exploratory','optimization':'one fixed rule, no parameter scan','status':'NOT_READY'}
 b=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');waves=detect(d)
 decision=lambda rs:[{k:v for k,v in w.items() if k not in ['end','end_reason']} for w in rs]
 for cut in [500,2000,3500]:assert decision(detect(d.iloc[:cut]))==decision([w for w in waves if w['i']<cut])
 rows=[]
 for w in waves:
  i=w['i'];progress=w['side']*(d.close.iloc[i+1:w['end']+1].to_numpy()-w['entry']);mfe=max(0.,float(progress.max())) if len(progress) else 0.;mae=max(0.,float(-progress.min())) if len(progress) else 0.;hit=mfe>=2*w['atr'];out='EXTENDED_2ATR' if hit else ('STRUCTURE_FAILED' if w['end_reason']=='STRUCTURE_BREAK' else 'UNRESOLVED')
  rows.append({'period':'earlier' if d.ts.iloc[i]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':w['side'],'entry':w['entry'],'invalidation':w['invalidation'],'outcome':out,'max_favorable_points':mfe,'max_adverse_points':mae,'end_displacement_points':float(progress[-1]) if len(progress) else 0.})
 refs=[]
 for seg,g in d.groupby('seg'):
  off=int(g.index[0])
  for leg in legs(g.close.to_numpy(),10):
   a=off+leg['start'];b=off+leg['end'];dr=leg['direction'];matched=[w for w in waves if w['side']==dr and a<=w['i']<b];active=any(w['side']==dr and w['i']<a<=w['end'] for w in waves);first=min(matched,key=lambda w:w['i']) if matched else None
   refs.append({'period':'earlier' if d.ts.iloc[a]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','new_signal':bool(first),'already_active':active,'delay':first['i']-a if first else None,'moved':float(dr*(d.close.iloc[first['i']]-d.close.iloc[a])) if first else None})
 summary=[]
 for period in ['earlier','later']:
  rr=[x for x in rows if x['period']==period];ref=[x for x in refs if x['period']==period];mm=[x for x in ref if x['new_signal']]
  summary.append({'period':period,'waves':len(rr),'outcomes':{k:sum(x['outcome']==k for x in rr) for k in ['EXTENDED_2ATR','STRUCTURE_FAILED','UNRESOLVED']},'median_favorable_points':float(np.median([x['max_favorable_points'] for x in rr])) if rr else None,'median_adverse_points':float(np.median([x['max_adverse_points'] for x in rr])) if rr else None,'median_end_displacement_points':float(np.median([x['end_displacement_points'] for x in rr])) if rr else None,'reference_legs':len(ref),'new_matching_signal_legs':len(mm),'uncovered_legs':sum(not x['new_signal'] and not x['already_active'] for x in ref),'median_matched_delay_minutes':float(np.median([x['delay'] for x in mm])) if mm else None,'median_matched_moved_points':float(np.median([x['moved'] for x in mm])) if mm else None})
 pd.DataFrame(rows).to_csv(P/'waves_derived.csv',index=False);result={'summary':summary,'prefix_checks':3,'status':'NOT_READY','warning':'Wave extension not trade success. Reference pivots are posthoc evaluation only, distinct from causal2right pivots. All data consumed.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
