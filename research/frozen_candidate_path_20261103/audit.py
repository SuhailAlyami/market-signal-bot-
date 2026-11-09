"""Path-risk audit of unchanged selective5m candidate, no model tuning."""
import sys,json
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent;sys.path.insert(0,str(P.parent/'multiframe_unified'))
import run as base

def barriers(b,e,a,side):
 for k,x in enumerate(b.itertuples(),1):
  opening=side*(x.open-e)/a
  if opening>=2:return 'TARGET',k
  if opening<=-1:return 'STOP',k
  favorable=(x.high-e)/a if side>0 else (e-x.low)/a;adverse=(e-x.low)/a if side>0 else (x.high-e)/a
  if favorable>=2 and adverse>=1:return 'AMBIGUOUS',k
  if favorable>=2:return 'TARGET',k
  if adverse>=1:return 'STOP',k
 return 'TIMEOUT',None

def main():
 cfg={'candidate':'unchanged5m price selective walkforward10/12 endpoints','primary_metric':'same30min endpoint sign unchanged','additional_diagnostic':'MFE/MAE on native5min OHLC;2ATR-before1ATR within30min, opening precedence, both intrabar ambiguous not success','entry':'close and next5min open sensitivity; no executable fills or options PnL assumed','status':'NOT_READY; no retraining or filtering'};(P/'PROTOCOL.json').write_text(json.dumps(cfg,indent=2))
 raw=base.raw(base.P/'raw/SPX_FIVE_MINS.json');es=base.raw(base.P/'raw/ES_FIVE_MINS.json');d,_=base.prepare(raw,es,5);lookup={t:i for i,t in enumerate(d.available)};signals=pd.read_csv(P.parent/'multiframe_walkforward/signals_derived.csv');signals=signals[(signals.frame=='FIVE_MINS')&(signals.variant=='price')&(signals.policy=='selective')];out=[];excluded=[]
 for r in signals.itertuples():
  t=pd.Timestamp(r.decision_Riyadh).tz_convert('UTC');i=lookup[t];side=int(r.side)
  if i+6>=len(d) or d.seg.iloc[i]!=d.seg.iloc[i+6] or d.session.iloc[i]!=d.session.iloc[i+6]:excluded.append(str(t));continue
  b=d.iloc[i+1:i+7];a=float(d.atr.iloc[i])
  for entry in ['close','next_open']:
   e=float(d.close.iloc[i] if entry=='close' else b.open.iloc[0]);favorable=max(0.,float(b.high.max()-e if side>0 else e-b.low.min()));adverse=max(0.,float(e-b.low.min() if side>0 else b.high.max()-e));endpoint=side*(float(b.close.iloc[-1])-e);result,k=barriers(b,e,a,side)
   if entry=='close':assert np.isclose(endpoint,r.signed_points)
   out.append({'decision_Riyadh':r.decision_Riyadh,'side':side,'entry':entry,'endpoint_signed_points':endpoint,'endpoint_correct':endpoint>0,'favorable_points':favorable,'adverse_points':adverse,'adverse_ATR':adverse/a,'barrier_result_30min':result,'barrier_5min_bar_number':k})
 df=pd.DataFrame(out);df.to_csv(P/'path_cases_derived.csv',index=False);summary=[]
 for entry,g in df.groupby('entry',sort=False):
  summary.append({'entry':entry,'scored':len(g),'endpoint_hits':int(g.endpoint_correct.sum()),'median_max_adverse_points':float(g.adverse_points.median()),'max_adverse_points':float(g.adverse_points.max()),'median_max_adverse_ATR':float(g.adverse_ATR.median()),'positive_endpoints_with_at_least1ATR_adverse_anytime':int((g.endpoint_correct&(g.adverse_ATR>=1)).sum()),'barrier_outcomes':g.barrier_result_30min.value_counts().to_dict()})
 result={'summary':summary,'signals':len(signals),'incomplete_horizon_excluded':len(excluded),'excluded_times':excluded,'status':'NOT_READY','warning':'Additional risk diagnostic, not a redefinition or invalidation of endpoint metric.5min intrabar ordering unresolved conservatively. No options profit calculated.'};(P/'RESULT.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
