import json,csv,datetime,contextlib,io
from pathlib import Path
from zoneinfo import ZoneInfo
from cfd_causal_reference import Bar,directions
from early_metric import score
p=Path(__file__).parent;out={}
for sym,path in [('SPX',p/'spx.csv'),('ES',p/'archive_es/spx.csv'),('NQ',p/'archive_nq/spx.csv')]:
 bs=[Bar(int(r['time']),*[float(r[k]) for k in ['open','high','low','close']]) for r in csv.DictReader(path.open())]
 models={k:[0]*len(bs) for k in ['opening_range5_break','opening_range5_failure']};date=None;opening=[];hi=lo=None;previous=None;fired=set()
 for i,b in enumerate(bs):
  local=datetime.datetime.fromtimestamp(b.time/1000,datetime.timezone.utc).astimezone(ZoneInfo('America/New_York'));m=local.hour*60+local.minute
  if local.date()!=date:date=local.date();opening=[];hi=lo=None;previous=None;fired=set()
  if 570<=m<575:opening.append(b)
  if m==575 and len(opening)==5 and opening[0].time==b.time-300000 and all(y.time-x.time==60000 for x,y in zip(opening,opening[1:])):hi=max(x.high for x in opening);lo=min(x.low for x in opening)
  if hi is not None and 575<=m<960 and directions(bs[max(0,i-30):i+1])[0]:
   continuous=previous is not None and b.time-previous.time==60000
   side=1 if b.close>hi and continuous and previous.close<=hi else -1 if b.close<lo and continuous and previous.close>=lo else 0
   if side and ('break',side) not in fired:models['opening_range5_break'][i]=side;fired.add(('break',side))
   fail=-1 if continuous and previous.close>hi and lo<=b.close<hi else 1 if continuous and previous.close<lo and lo<b.close<=hi else 0
   if fail and ('failure',fail) not in fired:models['opening_range5_failure'][i]=fail;fired.add(('failure',fail))
  previous=b
 result=score(bs,models)
 for v in result['models'].values():v.pop('matches',None)
 out[sym]=result
 print(sym,{k:(v['matched'],v['signals_evaluable']) for k,v in result['models'].items()})
(p/'session_time_results.json').write_text(json.dumps(out,indent=2))
