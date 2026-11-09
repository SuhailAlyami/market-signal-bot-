import csv,json,math
from pathlib import Path
from cfd_causal_reference import Bar,directions
from cfd_acceleration_v4 import acceleration
from cfd_path_scoring_v2 import outcome
p=Path(__file__).parent
bs=[Bar(int(r['time']),*[float(r[k]) for k in ['open','high','low','close']]) for r in csv.DictReader((p/'spx.csv').open())]
n=len(bs);ema20=[];ema50=[];rsi=[];gain=loss=None;changes=[];pivlo=[];pivhi=[];signals={k:[] for k in ['v4_impulse','v3_ready','failed_break','range_break10','trend_pullback','rsi_reentry','confirmed_divergence','double_bottom_top','flag_contraction']}
for i,b in enumerate(bs):
 contiguous=i and b.time-bs[i-1].time==60000
 if not contiguous:
  gain=loss=None;changes=[];pivlo=[];pivhi=[]
 ema20.append(b.close if not contiguous else ema20[-1]+2/21*(b.close-ema20[-1]))
 ema50.append(b.close if not contiguous else ema50[-1]+2/51*(b.close-ema50[-1]))
 if contiguous:
  delta=b.close-bs[i-1].close;changes.append(delta)
  if gain is None and len(changes)>=14:
   gain=sum(max(x,0) for x in changes[-14:])/14;loss=sum(max(-x,0) for x in changes[-14:])/14
  elif gain is not None:
   gain=(gain*13+max(delta,0))/14;loss=(loss*13+max(-delta,0))/14
 rv=None if gain is None else 50 if gain==loss==0 else 100 if loss==0 else 100-100/(1+gain/loss)
 rsi.append(rv)
 valid,ready,failed=directions(bs[:i+1]);ds={k:0 for k in signals}
 if valid:
  ds['v4_impulse']=acceleration(bs[:i+1]);ds['v3_ready']=ready;ds['failed_break']=failed
  hi=max(x.high for x in bs[i-10:i]);lo=min(x.low for x in bs[i-10:i])
  ds['range_break10']=1 if b.close>hi and bs[i-1].close<=hi else -1 if b.close<lo and bs[i-1].close>=lo else 0
  ds['trend_pullback']=1 if ema20[i]>ema50[i] and bs[i-1].close<=ema20[i-1] and b.close>ema20[i] else -1 if ema20[i]<ema50[i] and bs[i-1].close>=ema20[i-1] and b.close<ema20[i] else 0
  if rv is not None and rsi[i-1] is not None:
   ds['rsi_reentry']=1 if rsi[i-1]<=30<rv else -1 if rsi[i-1]>=70>rv else 0
  # Pivot at i-2 is first knowable now. Never timestamp the signal at pivot.
  j=i-2
  if rsi[j] is not None:
   win=bs[j-2:j+3]
   if all(bs[k].time-bs[k-1].time==60000 for k in range(j-1,i+1)):
    if bs[j].low<min(x.low for x in win[:2]+win[3:]):
     if pivlo and bs[j].low<bs[pivlo[-1]].low and rsi[j]>rsi[pivlo[-1]]:ds['confirmed_divergence']=1
     pivlo.append(j)
    if bs[j].high>max(x.high for x in win[:2]+win[3:]):
     if pivhi and bs[j].high>bs[pivhi[-1]].high and rsi[j]<rsi[pivhi[-1]]:ds['confirmed_divergence']=-1 if ds['confirmed_divergence']==0 else 0
     pivhi.append(j)
 if valid:
  atr=sum(max(bs[j].high-bs[j].low,abs(bs[j].high-bs[j-1].close),abs(bs[j].low-bs[j-1].close)) for j in range(i-20,i))/20
  # Strict confirmed pivots; neckline signal only when the current close crosses.
  if len(pivlo)>=2:
   a,z=pivlo[-2:]
   if 5<=z-a<=60 and i-z<=30 and abs(bs[a].low-bs[z].low)<=.5*atr:
    neck=max(x.high for x in bs[a:z+1])
    if bs[i-1].close<=neck<b.close:ds['double_bottom_top']=1
  if len(pivhi)>=2:
   a,z=pivhi[-2:]
   if 5<=z-a<=60 and i-z<=30 and abs(bs[a].high-bs[z].high)<=.5*atr:
    neck=min(x.low for x in bs[a:z+1])
    if bs[i-1].close>=neck>b.close:ds['double_bottom_top']=-1 if ds['double_bottom_top']==0 else 0
  pole=bs[i-6].close-bs[i-11].close
  hi=max(x.high for x in bs[i-5:i]);lo=min(x.low for x in bs[i-5:i])
  narrow=hi-lo<=1.5*atr
  if narrow and pole>=2*atr and bs[i-1].close<=hi<b.close:ds['flag_contraction']=1
  if narrow and pole<=-2*atr and bs[i-1].close>=lo>b.close:ds['flag_contraction']=-1
 for k,d in ds.items():signals[k].append(d)
def evaluate(ds,left,right):
 out=[];last=-10**20;busy=-1
 for i in range(max(31,left),min(right,n-1)):
  if not ds[i] or i<=busy or bs[i].time-last<600000:continue
  s=ds[i];atr=sum(max(bs[j].high-bs[j].low,abs(bs[j].high-bs[j-1].close),abs(bs[j].low-bs[j-1].close)) for j in range(i-20,i))/20
  entry=bs[i+1].open;result='pending';last=bs[i].time
  for j in range(i+1,min(i+11,right,n)):
   busy=j
   if bs[j].time-bs[j-1].time!=60000:result='gap';break
   result=outcome(s,entry,atr,bs[j].open,bs[j].high,bs[j].low)
   if result!='pending':break
  if result=='pending' and busy==i+10:result='timeout'
  out.append({'decision':bs[i].time+60000,'direction':s,'result':result})
 from collections import Counter
 c=dict(Counter(x['result'] for x in out));return {'counts':c,'N':len(out),'conservative_target_share':c.get('target',0)/len(out) if out else None,'events':out}
cut=n*2//3
report={'status':'EXPLORATORY_NOT_EARLY_PRECISION','cut_bar':cut,'models':{k:{'development':evaluate(ds,0,cut),'later_inspected':evaluate(ds,cut,n)} for k,ds in signals.items()},'limits':'Fixed diagnostic 1ATR target/.75ATR adverse/10m, next-open reference. No costs. All dates inspected, no blind holdout. Two bars confirmation delay for divergences. EMA/RSI reset at gaps. No parameter search.'}
(p/'chart_patterns.json').write_text(json.dumps(report,indent=2))
for k,v in report['models'].items():print(k,json.dumps({s:{a:b for a,b in x.items() if a!='events'} for s,x in v.items()}))
