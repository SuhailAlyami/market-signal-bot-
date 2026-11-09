import csv,json
from pathlib import Path
from cfd_path_scoring_v2 import outcome
p=Path(__file__).parent
bars=list(csv.DictReader((p/'spx.csv').open()))
for b in bars:
 for k in b:b[k]=float(b[k])
idx={int(b['time']):i for i,b in enumerate(bars)}
es=json.loads((p/'result.json').read_text())['events'];cut=44
out={}
for mode in ['original','reverse','one_bar_confirm']:
 results=[]
 for e in es:
  i=idx.get(e['decision_at']);s=e['direction']*(-1 if mode=='reverse' else 1);a=e['atr']
  if i is None:results.append('gap');continue
  if mode=='one_bar_confirm':
   b=bars[i]
   if s*(b['close']-b['open'])<=0:results.append('filtered');continue
   i+=1
  if i>=len(bars):results.append('pending');continue
  entry=bars[i]['open'];answer='pending';expected=bars[i]['time']
  for b in bars[i:i+10]:
   if b['time']!=expected:answer='gap';break
   expected+=60000
   answer=outcome(s,entry,a,b['open'],b['high'],b['low'])
   if answer!='pending':break
  if answer=='pending' and len(bars[i:i+10])==10:answer='timeout'
  results.append(answer)
 def score(x):
  from collections import Counter
  c=dict(Counter(x));n=len(x)-c.get('filtered',0);return {'counts':c,'retained':n,'conservative_target_share':c.get('target',0)/n if n else None}
 out[mode]={'development':score(results[:cut]),'later_inspected':score(results[cut:]),'all':score(results)}
(p/'alternatives.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
