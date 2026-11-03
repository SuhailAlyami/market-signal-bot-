import csv,json,math
from pathlib import Path
from cfd_causal_reference import Bar,directions
from cfd_acceleration_v4 import acceleration
from cfd_path_scoring_v2 import outcome
p=Path(__file__).parent
bs=[Bar(int(r['time']),*[float(r[k]) for k in ['open','high','low','close']]) for r in csv.DictReader((p/'spx.csv').open())]
n=len(bs);ema12=[];ema26=[];macd=[];macds=[];ema20=[];ema50=[];rsi=[];gain=loss=None;changes=[];pivlo=[];pivhi=[];signals={k:[] for k in ['v4_impulse','v3_ready','failed_break','range_break10','trend_pullback','rsi_reentry','confirmed_divergence','macd_cross','macd_trend','macd_trend_body','break_retest','retest_macd','macd_trend_rsi','retest_macd_rsi']}
for i,b in enumerate(bs):
 contiguous=i and b.time-bs[i-1].time==60000
 if not contiguous:
  gain=loss=None;changes=[];pivlo=[];pivhi=[]
 ema12.append(b.close if not contiguous else ema12[-1]+2/13*(b.close-ema12[-1]))
 ema26.append(b.close if not contiguous else ema26[-1]+2/27*(b.close-ema26[-1]))
 macd.append(ema12[-1]-ema26[-1])
 macds.append(macd[-1] if not contiguous else macds[-1]+.2*(macd[-1]-macds[-1]))
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
  cross=1 if macd[i]>macds[i] and macd[i-1]<=macds[i-1] else -1 if macd[i]<macds[i] and macd[i-1]>=macds[i-1] else 0
  trend=1 if ema20[i]>ema50[i] else -1 if ema20[i]<ema50[i] else 0
  ds['macd_cross']=cross
  ds['macd_trend']=cross if cross==trend else 0
  body=abs(b.close-b.open)/(b.high-b.low) if b.high>b.low else 0
  ds['macd_trend_body']=cross if cross==trend and body>=.6 and cross*(b.close-b.open)>0 else 0
  # Prior bar breaks its previous 10-bar range; current bar retests that known level.
  levelhi=max(x.high for x in bs[i-11:i-1]);levello=min(x.low for x in bs[i-11:i-1])
  retest=1 if bs[i-1].close>levelhi and b.low<=levelhi and b.close>levelhi and b.close>b.open else -1 if bs[i-1].close<levello and b.high>=levello and b.close<levello and b.close<b.open else 0
  ds['break_retest']=retest
  ds['retest_macd']=retest if retest==trend and retest*(macd[i]-macds[i])>0 else 0
  ds['v4_impulse']=acceleration(bs[:i+1]);ds['v3_ready']=ready;ds['failed_break']=failed
  hi=max(x.high for x in bs[i-10:i]);lo=min(x.low for x in bs[i-10:i])
  ds['range_break10']=1 if b.close>hi and bs[i-1].close<=hi else -1 if b.close<lo and bs[i-1].close>=lo else 0
  ds['trend_pullback']=1 if ema20[i]>ema50[i] and bs[i-1].close<=ema20[i-1] and b.close>ema20[i] else -1 if ema20[i]<ema50[i] and bs[i-1].close>=ema20[i-1] and b.close<ema20[i] else 0
  ds['macd_trend_rsi']=cross if rv is not None and cross==trend and ((cross==1 and 50<rv<70) or (cross==-1 and 30<rv<50)) else 0
  ds['retest_macd_rsi']=retest if rv is not None and ds['retest_macd'] and ((retest==1 and 50<rv<70) or (retest==-1 and 30<rv<50)) else 0
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
(p/'macd_comparison.json').write_text(json.dumps(report,indent=2))
for k,v in report['models'].items():print(k,json.dumps({s:{a:b for a,b in x.items() if a!='events'} for s,x in v.items()}))
