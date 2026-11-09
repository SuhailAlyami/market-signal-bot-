"""Consumed last-fold numerical reproduction, never new forward evidence."""
import json
import numpy as np,pandas as pd
from replay import P,base,verified_model,predict

def main():
 root=P.parent/'multiframe_walkforward';recipe_path=root/'CANDIDATE_NEXT_TEST.json';recipe=json.loads(recipe_path.read_text());recipe,model=verified_model(recipe_path,root/recipe['model_file']);d,es=base.prepare(base.raw(base.P/'raw/SPX_FIVE_MINS.json'),base.raw(base.P/'raw/ES_FIVE_MINS.json'),5);tf=base.ft.technical(d,es);pf=base.ft.patterns(d);f=pd.concat([tf,pf],axis=1);p=predict(f,model);common=np.isfinite(f.values).all(1);score=np.maximum(p,1-p);candidate=common&(pf.values!=0).any(1)&(score>=model['threshold']);log=pd.read_csv(root/'signals_derived.csv');log=log[(log.frame=='FIVE_MINS')&(log.variant=='price')&(log.policy=='selective')];lookup={t:i for i,t in enumerate(d.available)};start=int(model['test_start']);expected=log[log.fold_start==start];prior=log[log.fold_start<start];lastslot=None
 if len(prior):lastslot=int(d.slot.iloc[lookup[pd.Timestamp(prior.iloc[-1].decision_Riyadh).tz_convert('UTC')]])
 actual=[]
 for i in np.flatnonzero(candidate&(np.arange(len(d))>=start)&(np.arange(len(d))<start+100)):
  slot=int(d.slot.iloc[i])
  if lastslot is not None and slot-lastslot<10:continue
  lastslot=slot;side=1 if p[i]>=.5 else -1;actual.append({'decision_Riyadh':str(d.available.iloc[i].tz_convert('Asia/Riyadh')),'side':side});cut=i+1
  shortf=pd.concat([base.ft.technical(d.iloc[:cut],es),base.ft.patterns(d.iloc[:cut])],axis=1);assert np.isclose(predict(shortf,model)[i],p[i],rtol=0,atol=1e-12)
 exp=[{'decision_Riyadh':r.decision_Riyadh,'side':int(r.side)} for r in expected.itertuples()];assert actual==exp,(actual,exp);scored=expected[expected.scorable];hits=int((scored.signed_points>0).sum());allscored=log[log.scorable]
 result={'status':'CONSUMED_NUMERICAL_REPRODUCTION_ONLY_NOT_READY','frozen_model_hash_verified':True,'last_fold_start':start,'signals_expected':len(exp),'signals_reproduced':len(actual),'exact_decision_direction_match':True,'past_score_unchanged_when_future_removed':True,'frozen_latest_weights_own_out_of_fit_sample':{'scored':len(scored),'hits':hits},'whole_walkforward_procedure_sample':{'scored':len(allscored),'hits':int((allscored.signed_points>0).sum()),'different_fold_models':int(log.fold_start.nunique())},'model_and_threshold_unchanged':True,'new_forward_evidence_added':0};(P/'FROZEN_REPRODUCTION.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
