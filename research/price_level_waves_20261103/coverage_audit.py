"""Posthoc wave opportunity coverage. Future extrema for scoring only."""
import json
import numpy as np,pandas as pd
import run as r
from reference_legs import legs
P=r.P

def main():
 d=r.ev.add_atr(r.ev.add_structure(r.readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');waves=r.detect(d);rows=[]
 for seg,g in d.groupby('seg',sort=False):
  offset=int(g.index[0])
  for x in legs(g.close.to_numpy(),10):
   a=offset+x['start'];b=offset+x['end'];side=x['direction'];matching=[w for w in waves if w['side']==side and a<=w['i']<b];active=[w for w in waves if w['side']==side and w['i']<a and w['end']>=a];w=min(matching,key=lambda z:z['i']) if matching else None
   prior=[z for z in waves if z['i']<a and d.seg.iloc[z['i']]==seg];prev=max(prior,key=lambda z:z['i']) if prior else None
   locked=bool(prev and prev['side']==side and prev['end']<a and not any(a<=z['i']<b for z in waves))
   total=side*(d.close.iloc[b]-d.close.iloc[a]);moved=side*(d.close.iloc[w['i']]-d.close.iloc[a]) if w else None
   rows.append({'period':'earlier' if d.ts.iloc[a]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','start_Riyadh':str((d.ts.iloc[a]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'direction':side,'points':float(total),'complete':x['complete'],'duration_minutes':b-a,'new_matching_signal':bool(w),'already_active_same_direction':bool(active),'no_new_signal_and_same_direction_lock_at_start':locked,'warmup_at_start':bool(d.pos.iloc[a]<21),'delay_minutes':int(w['i']-a) if w else None,'moved_before_signal_points':float(moved) if w else None,'remaining_to_extreme_points':float(total-moved) if w else None})
 pd.DataFrame(rows).to_csv(P/'reference_coverage_derived.csv',index=False);summary=[]
 for period in ['earlier','later']:
  rr=[x for x in rows if x['period']==period];matches=[x for x in rr if x['new_matching_signal']];uncovered=[x for x in rr if not x['new_matching_signal'] and not x['already_active_same_direction']]
  summary.append({'period':period,'reference_legs':len(rr),'new_matching_signal_legs':len(matches),'already_active_legs':sum(x['already_active_same_direction'] for x in rr),'legs_with_neither_new_signal_nor_existing_direction':len(uncovered),'same_direction_locked_at_start_without_any_new_signal':sum(x['no_new_signal_and_same_direction_lock_at_start'] for x in uncovered),'median_delay_matched_minutes':float(np.median([x['delay_minutes'] for x in matches])) if matches else None,'median_moved_before_signal_points':float(np.median([x['moved_before_signal_points'] for x in matches])) if matches else None,'median_remaining_to_extreme_points':float(np.median([x['remaining_to_extreme_points'] for x in matches])) if matches else None})
 out={'summary':summary,'threshold_points':10,'warning':'Posthoc 10-point close-based directional-change legs, not live labels or signal precision. Active and newly signaled counts can overlap. Incomplete last legs retained and marked. Lock attribution is conservative descriptive, not a causal counterfactual.','status':'NOT_READY'};(P/'COVERAGE_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
