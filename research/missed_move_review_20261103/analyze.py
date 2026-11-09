"""Posthoc explanatory audit; never a live event detector or retuning step."""
import sys,json
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'frozen_replay'))
import early_move_eval_openfix as ev
from features import features

def legs(closes,threshold=10):
 if len(closes)<2:return []
 lo=hi=0;side=0;start=ext=0;out=[]
 for i in range(1,len(closes)):
  v=closes[i]
  if side==0:
   if v<closes[lo]:lo=i
   if v>closes[hi]:hi=i
   if v-closes[lo]>=threshold:side=1;start=lo;ext=i
   elif closes[hi]-v>=threshold:side=-1;start=hi;ext=i
   continue
  if side*(v-closes[ext])>0:ext=i
  elif side*(closes[ext]-v)>=threshold:
   out.append({'start':start,'end':ext,'direction':side,'confirmed_at':i,'complete':True});start=ext;ext=i;side=-side
 if side and side*(closes[ext]-closes[start])>=threshold:out.append({'start':start,'end':ext,'direction':side,'confirmed_at':None,'complete':False})
 return out

def main():
 raw=pd.read_csv(P.parent/'nov2_final_review/SPX_20261102.csv');raw['ts']=pd.to_datetime(raw.pop('timestamp'),utc=True);d=ev.add_atr(ev.add_structure(raw),'prior20');f=features(d);state=json.loads((P.parent/'nov2_final_review/frozen_state.json').read_text());model=json.loads((P.parent/'frozen_replay/MODEL.json').read_text());lookup={str(ts+pd.Timedelta(minutes=1)):i for i,ts in enumerate(d.ts)}
 outattrs=[]
 for s in state['signals']:
  i=lookup[s['decision_utc']];x=f.iloc[i].values;row={'decision_Riyadh':s['decision_Riyadh'],'side':s['direction'],'close_result':s['close_result'],'close':float(d.close.iloc[i])}
  for name in ['timing','direction']:
   m=model['models'][name];terms=((x-np.array(m['mean']))/np.array(m['scale']))*np.array(m['coefficient']);total=float(m['intercept']+terms.sum());price=float(m['intercept']+terms[:6].sum());clock=float(terms[6:].sum());row[name+'_explanation']={'logit':total,'score_uncalibrated':float(1/(1+np.exp(-total))),'price_plus_intercept':price,'clock_contribution':clock,'terms':dict(zip(model['feature_order'],map(float,terms)))}
  row['clock_flips_direction_vs_price_only']=bool((row['direction_explanation']['price_plus_intercept']>=0)!=(row['direction_explanation']['logit']>=0));outattrs.append(row)
 sig=[(lookup[s['decision_utc']],s['direction'],s['decision_Riyadh']) for s in state['signals']];segments=[]
 for leg in legs(d.close.values):
  a,b=leg['start'],leg['end'];side=leg['direction'];matches=[(i,t) for i,dr,t in sig if dr==side and a<=i<=b];first=matches[0] if matches else None;starttime=d.ts.iloc[a]+pd.Timedelta(minutes=1);endtime=d.ts.iloc[b]+pd.Timedelta(minutes=1)
  segments.append({'start_Riyadh':str(starttime.tz_convert('Asia/Riyadh')),'end_Riyadh':str(endtime.tz_convert('Asia/Riyadh')),'direction':int(side),'points':float(side*(d.close.iloc[b]-d.close.iloc[a])),'duration_minutes':b-a,'retrospective_reversal_confirmed':leg['complete'],'first_matching_model_signal':first[1] if first else None,'points_already_moved_before_match':float(side*(d.close.iloc[first[0]]-d.close.iloc[a])) if first else None,'minutes_to_match':int(first[0]-a) if first else None,'starts_in_uncovered_first_hour':a<60})
 summary={'status':'POSTHOC_DIAGNOSTIC_NOT_READY','definition':'10-point directional-change legs on minute closes; extrema and onset known retrospectively; not a live signal','threshold_chosen_for_descriptive_review_only':10,'legs':len(segments),'legs_with_any_matching_signal_before_extreme':sum(x['first_matching_model_signal'] is not None for x in segments),'legs_without_matching_signal':sum(x['first_matching_model_signal'] is None for x in segments),'direction_clock_flip_signals':sum(x['clock_flips_direction_vs_price_only'] for x in outattrs),'largest_legs':sorted(segments,key=lambda x:x['points'],reverse=True)[:5],'warning':'Matching is retrospective opportunity coverage, not precision or early prediction; no model or trade rules changed'}
 (P/'summary.json').write_text(json.dumps(summary,indent=2));(P/'signal_attributions.json').write_text(json.dumps(outattrs,indent=2));pd.DataFrame(segments).to_csv(P/'retrospective_legs.csv',index=False);print(json.dumps(summary,indent=2));print('FAILURES',[(r['decision_Riyadh'],r['side'],round(r['direction_explanation']['price_plus_intercept'],3),round(r['direction_explanation']['clock_contribution'],3)) for r in outattrs if r['close_result']=='FAILURE'])
if __name__=='__main__':main()
