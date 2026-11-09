"""Common30-minute endpoint direction audit; no detector or filter changes."""
import importlib.util,json,hashlib,sys
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'structure_wave_research'))
import run as confirmed
spec=importlib.util.spec_from_file_location('early',P.parent/'early_structure_research/run.py');early=importlib.util.module_from_spec(spec);spec.loader.exec_module(early)

def evaluate(d,waves):
 rows=[];excluded=0
 for w in waves:
  i=w['i'];j=i+30
  if j>=len(d) or d.seg.iloc[i]!=d.seg.iloc[j]:excluded+=1;continue
  delta=float(d.close.iloc[j]-d.close.iloc[i]);signed=w['side']*delta
  rows.append({'period':'earlier' if d.ts.iloc[i]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'side':w['side'],'delta_points':delta,'signed_delta_points':signed,'direction_correct':signed>0,'flat':delta==0,'signed_delta_ATR':signed/w['atr']})
 return rows,excluded

def main():
 protocol={'purpose':'Common30-minute level endpoint direction, not candle shape or temporary excursion','horizon':30,'correct':'side*(close_t+30-close_t)>0; flat not success, report points and1ATR endpoint too','exclusion':'no30-minute contiguous same-session horizon excluded explicitly','models':'confirmed structure and earlier structure unchanged','sample':'consumed12sessions, audit chosen after prior results, exploratory only','baseline':'same times random direction preserving observed long share; no p or independence claim','status':'NOT_READY'}
 blob=json.dumps(protocol,indent=2).encode();(P/'PROTOCOL.json').write_bytes(blob);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest())
 d=confirmed.ev.add_atr(confirmed.ev.add_structure(confirmed.readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');out=[];details=[]
 for name,model in [('confirmed',confirmed),('early',early)]:
  rows,excluded=evaluate(d,model.detect(d))
  for x in rows:details.append(dict(model=name,**x))
  for period in ['earlier','later']:
   rr=[x for x in rows if x['period']==period];n=len(rr);p=np.mean([x['side']==1 for x in rr]) if n else 0;delta=np.array([x['delta_points'] for x in rr]);base=float(np.mean(p*(delta>0)+(1-p)*(delta<0))) if n else None
   out.append({'model':name,'period':period,'n':n,'direction_hits':sum(x['direction_correct'] for x in rr),'direction_rate':sum(x['direction_correct'] for x in rr)/n if n else None,'endpoint_at_least1ATR_hits':sum(x['signed_delta_ATR']>=1 for x in rr),'same_time_random_direction_expected':base,'flat':sum(x['flat'] for x in rr),'mean_signed_points':float(np.mean([x['signed_delta_points'] for x in rr])) if n else None,'median_signed_points':float(np.median([x['signed_delta_points'] for x in rr])) if n else None})
  out.append({'model':name,'excluded_incomplete_horizon_all_dates':excluded})
 pd.DataFrame(details).to_csv(P/'endpoint_cases_derived.csv',index=False);result={'rows':out,'status':'NOT_READY','warning':'30-minute endpoint audit chosen posthoc on consumed data. Positive endpoint does not imply safe path or options profit; no cost or trade exit execution.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
