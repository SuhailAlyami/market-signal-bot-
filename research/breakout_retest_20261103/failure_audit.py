"""Post-hoc diagnosis only; never a feature or filter."""
import json
import numpy as np,pandas as pd
import run as r
P=r.P

def outcome(b,e,a,side):
 for k,c in enumerate(b.itertuples(),1):
  op=side*(c.open-e)/a
  if op>=2:return 'TARGET'
  if op<=-1:return 'STOP'
  f=(c.high-e)/a if side>0 else (e-c.low)/a
  q=(e-c.low)/a if side>0 else (c.high-e)/a
  if f>=2 and q>=1:return 'AMBIGUOUS'
  if f>=2:return 'TARGET'
  if q>=1:return 'STOP'
 return 'TIMEOUT'

def main():
 d=r.ev.add_atr(r.ev.add_structure(r.readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');s=r.detect(d);dates=d.ts.dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d');rows=[];summary=[]
 for period,mask in [('earlier',dates<'2026-10-26'),('later',dates>='2026-10-26')]:
  last=None;ids=[]
  for i in np.flatnonzero(mask.values&(s!=0)):
   now=d.ts.iloc[i].timestamp()
   if last is None or now-last>=600:ids.append(i);last=now
  for entry in ['close','next_open']:
   lab=r.ev.label(d,entry);subset=[]
   for i in ids:
    if lab['status'][i]!=0:continue
    b=d.iloc[i+1:i+6];e=d.close.iloc[i] if entry=='close' else d.open.iloc[i+1];a=d.atr.iloc[i];side=s[i]
    o=outcome(b,e,a,side);assert (o=='TARGET')==bool(lab['up_c' if side>0 else 'dn_c'][i])
    favorable=(b.high.max()-e)/a if side>0 else (e-b.low.min())/a
    reverse=(e-b.low.min())/a if side>0 else (b.high.max()-e)/a
    row={'period':period,'entry':entry,'decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':int(side),'outcome':o,'target_touched_ignoring_stop':bool(favorable>=2),'either_direction_2ATR_ignoring_stop':bool(max(favorable,reverse)>=2),'favorable_5min_ATR':float(favorable)};rows.append(row);subset.append(row)
   summary.append({'period':period,'entry':entry,'n':len(subset),'outcomes':{k:sum(x['outcome']==k for x in subset) for k in ['TARGET','STOP','TIMEOUT','AMBIGUOUS']},'direction_target_touch_ignoring_stop':sum(x['target_touched_ignoring_stop'] for x in subset),'either_direction_2ATR_ignoring_stop':sum(x['either_direction_2ATR_ignoring_stop'] for x in subset),'failed_then_target_after_stop_or_ambiguity':sum(x['outcome'] in ['STOP','AMBIGUOUS'] and x['target_touched_ignoring_stop'] for x in subset)})
 pd.DataFrame(rows).to_csv(P/'failure_cases_derived.csv',index=False)
 result={'summary':summary,'limits':'Post-hoc diagnostic on consumed data. Ignoring stops is not a tradable result, not precision, and is not used to redefine success. No parameter tuning.','status':'NOT_READY'};(P/'FAILURE_AUDIT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
