import json,csv,datetime
from pathlib import Path
p=Path(__file__).parent
bars=list(csv.DictReader((p/'spx.csv').open()))
for b in bars:
 for k in b:b[k]=float(b[k])
index={int(b['time'])+60000:i for i,b in enumerate(bars)}
events=json.loads((p/'result.json').read_text())['events']
rows=[]
for e in events:
 i=index[e['decision_at']];b=bars[i];prev=bars[i-10:i];s=e['direction'];a=e['atr'];span=b['high']-b['low']
 rows.append(dict(**e,body=abs(b['close']-b['open'])/span,range_atr=span/a,trend=s*(b['close']-bars[i-5]['close'])/a,prior_trend=s*(bars[i-1]['close']-bars[i-6]['close'])/a,extension=s*(b['close']-sum(x['close'] for x in prev)/10)/a))
filters={'unchanged':lambda r:True,'prior_trend_aligned':lambda r:r['prior_trend']>0,'prior_trend_opposed':lambda r:r['prior_trend']<0,'range_max_2atr':lambda r:r['range_atr']<=2,'body_min_80pct':lambda r:r['body']>=.8,'extension_max_2atr':lambda r:r['extension']<=2}
def score(rs,f):
 kept=[r for r in rs if f(r)];wins=sum(r['result']=='target' for r in kept);loss=sum(r['result']=='stop' for r in kept)
 return dict(retained=len(kept),wins=wins,losses=loss,other=len(kept)-wins-loss,conservative_precision=wins/len(kept) if kept else None,retained_original_wins=wins,removed_original_wins=sum(r['result']=='target' for r in rs)-wins)
cut=len(rows)*2//3
out={'status':'EXPLORATORY_NOT_HOLDOUT','split_events':cut,'filters':{n:{'train':score(rows[:cut],f),'validation':score(rows[cut:],f),'all':score(rows,f)} for n,f in filters.items()},'events':rows,'limits':'Posthoc feature study on already inspected sample. Filtering original event stream does not replay state; not production performance or explosion recall.'}
(p/'failure_analysis.json').write_text(json.dumps(out,indent=2))
print(json.dumps(out['filters'],indent=2))
