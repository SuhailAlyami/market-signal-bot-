"""Operational early-event matching. Research metric, not trade P&L."""
import json,runpy,contextlib,io,statistics
from pathlib import Path

def movement(bars,t):
 if t<31 or t+5>=len(bars):return None
 if any(bars[j].time-bars[j-1].time!=60000 for j in range(t-30,t+6)):return None
 atr=sum(max(bars[j].high-bars[j].low,abs(bars[j].high-bars[j-1].close),abs(bars[j].low-bars[j-1].close)) for j in range(t-20,t))/20
 if atr<=0:return None
 price=bars[t].close;states={1:0,-1:0}
 for j in range(t+1,t+6):
  b=bars[j]
  for s in (1,-1):
   if states[s]:continue
   target=price+s*2*atr;stop=price-s*atr
   ot=s*(b.open-target)>=0;os=s*(b.open-stop)<=0
   ht=b.high>=target if s==1 else b.low<=target
   hs=b.low<=stop if s==1 else b.high>=stop
   states[s]=1 if ot else -1 if os else 2 if ht and hs else 1 if ht else -1 if hs else 0
  hits=[s for s in (1,-1) if states[s]==1]
  if len(hits)==1:return hits[0]
  if len(hits)>1:return 2
 return 2 if 2 in states.values() else 0

def score(bars,signal_map):
 labels={t:movement(bars,t) for t in range(31,len(bars)-5)}
 events=[];blocked=-1
 for t,d in labels.items():
  if t>blocked and d in (1,-1):events.append((t,d));blocked=t+5
 result={}
 for name,ds in signal_map.items():
  accepted=[];last=-10**20
  # Eligibility uses only past/current inputs supplied by model, not future labels.
  for t,d in enumerate(ds):
   if d and bars[t].time-last>=600000:
    accepted.append((t,d));last=bars[t].time
  evaluable=[(t,d) for t,d in accepted if labels.get(t) is not None]
  used=set();leads=[];matched=[]
  for t,d in evaluable:
   candidates=[(i,e) for i,e in enumerate(events) if i not in used and e[1]==d and 0<=e[0]-t<=3]
   if candidates:
    i,e=candidates[0];used.add(i);leads.append(e[0]-t);matched.append({'signal_bar':t,'event_anchor':e[0],'direction':d})
  tp=len(used);n=len(evaluable)
  result[name]={'signals_total':len(accepted),'signals_evaluable':n,'signals_unscorable':len(accepted)-n,'matched':tp,'unmatched_signals':n-tp,'events':len(events),'missed_events':len(events)-tp,'precision':tp/n if n else None,'recall':tp/len(events) if events else None,'median_lead_minutes':statistics.median(leads) if leads else None,'zero_lead_matches':sum(x==0 for x in leads),'matches':matched}
 return {'event_definition':'2 prior ATR directional move before 1 prior ATR adverse within next 5 contiguous minutes; greedy event anchors separated >5 bars; signal at anchor or <=3 minutes before; one-to-one','ambiguity_anchors':sum(d==2 for d in labels.values()),'models':result,'limits':'Anchors define an operational forward movement, NOT independently established physical onset. Zero-lead separated. All data consumed research, no holdout, costs or live accuracy claim. Unscorable signals retained separately.'}

if __name__=='__main__':
 p=Path(__file__).parent;output={}
 for source,path in [('SPX',p/'compare_head_shoulders.py'),('ES',p/'archive_es/compare_head_shoulders.py'),('NQ',p/'archive_nq/compare_head_shoulders.py')]:
  with contextlib.redirect_stdout(io.StringIO()):ns=runpy.run_path(str(path))
  result=score(ns['bs'],ns['signals']);output[source]=result
  print(source,{k:{a:b for a,b in v.items() if a!='matches'} for k,v in result['models'].items()},flush=True)
 (p/'early_metric_results.json').write_text(json.dumps(output,indent=2))
