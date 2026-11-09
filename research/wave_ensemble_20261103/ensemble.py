"""Causal union and independent-family agreement, no outcome-based selection."""
import sys,importlib.util,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
P=Path(__file__).resolve().parent
sys.path.insert(0,str(P.parent/'structure_wave_research'))
import early_move_eval_openfix as ev
from data_io import readzip

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
MODELS={n:load(n,P.parent/folder/'run.py') for n,folder in [('level','wave_level_research'),('confirmed','structure_wave_research'),('early','early_structure_research')]}
FAMILY={'level':'range','confirmed':'structure','early':'structure'}

def combine(d,books,mode):
 events=sorted(set(w['i'] for book in books.values() for w in book));out=[];last=None;lastseg=None
 for i in events:
  current={w['side'] for book in books.values() for w in book if w['i']==i}
  if len(current)!=1:continue
  side=next(iter(current));support=set();opposition=set()
  for name,book in books.items():
   for w in book:
    active=w['i']<=i<=w['end'] and not (i==w['end'] and w['end_reason']=='STRUCTURE_BREAK')
    if active and d.seg.iloc[w['i']]==d.seg.iloc[i]:
     (support if w['side']==side else opposition).add(FAMILY[name])
  if mode=='agreement' and (len(support)<2 or opposition):continue
  seg=int(d.seg.iloc[i]);t=d.ts.iloc[i].timestamp()
  if last is not None and seg==lastseg and t-last<600:continue
  out.append({'i':i,'side':side,'atr':float(d.atr.iloc[i]),'families':sorted(support)});last=t;lastseg=seg
 return out

def evaluate(d,signals):
 rows=[];excluded=0
 for w in signals:
  i=w['i'];j=i+30
  if j>=len(d) or d.seg.iloc[i]!=d.seg.iloc[j]:excluded+=1;continue
  delta=float(d.close.iloc[j]-d.close.iloc[i]);rows.append({'period':'earlier' if d.ts.iloc[i]<pd.Timestamp('2026-10-26',tz='UTC') else 'later','decision_Riyadh':str((d.ts.iloc[i]+pd.Timedelta(minutes=1)).tz_convert('Asia/Riyadh')),'side':w['side'],'delta':delta,'signed_points':w['side']*delta,'hit':w['side']*delta>0})
 return rows,excluded

def main():
 cfg={'hypotheses':['union of all three existing wave detectors','agreement of two DIFFERENT families at a new event, no active opposing family'],'families':FAMILY,'availability':'current event plus active states known by current close; never select historical winners','dedup':'same-time same-side once; conflicting new events discarded; shared10min cooldown reset segment','target':'fixed30min endpoint direction, flat failure; exclude incomplete same-segment horizon explicitly','sample':'consumed12 sessions, earlier7/later5 exploratory, not untouched holdout','optimization':'no best-model selection or parameter tuning','status':'NOT_READY'}
 b=json.dumps(cfg,indent=2).encode();(P/'PROTOCOL.json').write_bytes(b);(P/'PROTOCOL.sha256').write_text(hashlib.sha256(b).hexdigest())
 d=ev.add_atr(ev.add_structure(readzip(P.parent/'FirstRate_SPX_sample.zip','SPX_1min_sample.csv')),'prior20');books={k:m.detect(d) for k,m in MODELS.items()};candidates={k:combine(d,{k:v},'union') for k,v in books.items()};candidates.update({mode:combine(d,books,mode) for mode in ['union','agreement']})
 for cut in [500,2000,3500]:
  short=d.iloc[:cut];bb={k:m.detect(short) for k,m in MODELS.items()}
  for mode in ['union','agreement']:assert combine(short,bb,mode)==[w for w in candidates[mode] if w['i']<cut]
 result=[];details=[]
 for name,signals in candidates.items():
  rows,excluded=evaluate(d,signals)
  for x in rows:details.append(dict(model=name,**x))
  for period in ['earlier','later']:
   rr=[x for x in rows if x['period']==period];n=len(rr);p=np.mean([x['side']==1 for x in rr]) if n else 0;delta=np.array([x['delta'] for x in rr]);result.append({'model':name,'period':period,'n':n,'hits':sum(x['hit'] for x in rr),'rate':sum(x['hit'] for x in rr)/n if n else None,'same_times_random_direction_expected':float(np.mean(p*(delta>0)+(1-p)*(delta<0))) if n else None,'mean_signed_points':float(np.mean([x['signed_points'] for x in rr])) if n else None})
  result.append({'model':name,'excluded_horizon_all_dates':excluded})
 pd.DataFrame(details).to_csv(P/'signals_derived.csv',index=False);r={'rows':result,'prefix_checks':6,'status':'NOT_READY'};(P/'RESULT.json').write_text(json.dumps(r,indent=2));print(json.dumps(r,indent=2))
if __name__=='__main__':main()
