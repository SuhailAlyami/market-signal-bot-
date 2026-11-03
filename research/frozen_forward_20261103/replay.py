"""One-shot frozen research replay. No network, notifications, fitting or trading."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'multiframe_unified'))
import run as base

def verified_model(recipe_path,model_path):
 recipe=json.loads(recipe_path.read_text());blob=model_path.read_bytes()
 if hashlib.sha256(blob).hexdigest()!=recipe['sha256']:raise ValueError('frozen model hash mismatch')
 return recipe,json.loads(blob)

def closed(d,asof):
 t=pd.Timestamp(asof)
 if t.tzinfo is None:raise ValueError('asof timezone required')
 return d.loc[d.available<=t].reset_index(drop=True)

def predict(f,model):
 X=f[model['features']].to_numpy();valid=np.isfinite(X).all(1);p=np.full(len(f),np.nan);z=((X[valid]-np.array(model['mean']))/np.array(model['scale']))@np.array(model['coefficients'])+model['intercept'];p[valid]=1/(1+np.exp(-np.clip(z,-30,30)));return p

def insert_events(state,events):
 existing={s['decision_utc'] for s in state['signals']};added=0
 for e in events:
  if e['decision_utc'] in existing:continue
  if state.get('last_slot') is not None and e['slot']-state['last_slot']<10:continue
  state['signals'].append(e);existing.add(e['decision_utc']);state['last_slot']=e['slot'];added+=1
 return added

def replay(spx,es,asof,state_path,output_path):
 recipe_path=P.parent/'multiframe_walkforward/CANDIDATE_NEXT_TEST.json';recipe=json.loads(recipe_path.read_text());model_path=P.parent/'multiframe_walkforward'/recipe['model_file'];recipe,model=verified_model(recipe_path,model_path);start=recipe['future_evaluation_start_session'];identity={'model_sha256':recipe['sha256'],'start_session':start,'SPX_contract':416904,'ES_eligibility_contract':515416632,'step_minutes':5,'cooldown_trading_bars':10}
 if state_path.exists():
  state=json.loads(state_path.read_text())
  if state.get('identity')!=identity:raise ValueError('state identity mismatch; refusing silent reset')
 else:state={'identity':identity,'signals':[],'last_slot':None,'status':'NOT_READY'}
 d,ee=base.prepare(base.raw(spx),base.raw(es),5);d=closed(d,asof);ee=closed(ee,asof);tf=base.ft.technical(d,ee);pf=base.ft.patterns(d);features=pd.concat([tf,pf],axis=1);p=predict(features,model)
 # Historical price-only comparison had a shared49-feature availability mask.
 # Preserve it; ES volume values are NOT inputs to this46-feature predictor.
 common=np.isfinite(features.values).all(1);score=np.maximum(p,1-p);mask=common&(pf.values!=0).any(1)&(score>=model['threshold'])&(d.session>=start).values;events=[];now=pd.Timestamp(asof)
 for i in np.flatnonzero(mask):
  t=d.available.iloc[i];age=(now-t).total_seconds();events.append({'decision_utc':str(t),'decision_Riyadh':str(t.tz_convert('Asia/Riyadh')),'slot':int(d.slot.iloc[i]),'side':1 if p[i]>=.5 else -1,'reference_price':float(d.close.iloc[i]),'observed_at_utc':str(now),'observation':'RESEARCH_BACKFILL' if age>180 else 'RESEARCH_OBSERVED','provenance':'RESEARCH_ONLY','result':'PENDING'})
 added=insert_events(state,events);lookup={str(t):i for i,t in enumerate(d.available)}
 for s in state['signals']:
  if s['result']!='PENDING' or s['decision_utc'] not in lookup:continue
  i=lookup[s['decision_utc']];j=i+6
  if j<len(d):
   if d.seg.iloc[i]!=d.seg.iloc[j] or d.session.iloc[i]!=d.session.iloc[j]:s['result']='UNSCORABLE_SESSION_OR_GAP';continue
   delta=s['side']*(float(d.close.iloc[j])-s['reference_price']);s.update(result='CORRECT_ENDPOINT' if delta>0 else 'INCORRECT_ENDPOINT',signed_points=delta,evaluation_Riyadh=str(d.available.iloc[j].tz_convert('Asia/Riyadh')))
  elif len(d) and d.session.iloc[-1]>d.session.iloc[i]:s['result']='UNSCORABLE_SESSION_END'
 new=(d.session>=start).values;status='WAITING_FOR_NEW_SESSION_DATA' if not new.any() else ('BLOCKED_INCOMPLETE_FEATURES_OR_ES_ALIGNMENT' if not (new&common).any() else 'RESEARCH_ONLY_NOT_READY')
 report={'status':status,'asof_Riyadh':str(now.tz_convert('Asia/Riyadh')),'last_closed_SPX_Riyadh':str(d.available.iloc[-1].tz_convert('Asia/Riyadh')) if len(d) else None,'new_forward_bars':int(new.sum()),'new_bars_with_complete_features':int((new&common).sum()),'new_signals_recorded':added,'total_forward_signals':len(state['signals']),'frozen_model_verified':True,'model_feature_count':len(model['features']),'ES_used_for_shared_eligibility_only':True,'notifications_enabled':False,'continuous_monitoring':False}
 state_path.write_text(json.dumps(state,indent=2));output_path.write_text(json.dumps(report,indent=2));return report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--spx',type=Path,default=P/'SPX_latest_raw.json');p.add_argument('--es',type=Path,default=P/'ES_latest_raw.json');p.add_argument('--asof',default=pd.Timestamp.now(tz='UTC').isoformat());p.add_argument('--state',type=Path,default=P/'STATE.json');p.add_argument('--out',type=Path,default=P/'RESULT.json');a=p.parse_args();print(json.dumps(replay(a.spx,a.es,a.asof,a.state,a.out),indent=2))
