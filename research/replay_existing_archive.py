import csv,datetime,json,subprocess,sys,hashlib,shutil
from pathlib import Path
p=Path(__file__).parent
for sym in ['es','nq']:
 folder=p/('archive_'+sym);folder.mkdir(exist_ok=True)
 for name in ['cfd_causal_reference.py','cfd_acceleration_v4.py','cfd_path_scoring_v2.py','compare_macd.py','compare_head_shoulders.py']:shutil.copy(p/name,folder/name)
 with (p/(sym+'_old.csv')).open() as f, (folder/'spx.csv').open('w') as out:
  w=csv.writer(out);w.writerow(['time','open','high','low','close']);rows=list(csv.DictReader(f))
  for r in rows:w.writerow([int(datetime.datetime.fromisoformat(r['timestamp']).timestamp()*1000)]+[r[k] for k in ['Open','High','Low','Close']])
 print(sym,'running',len(rows),flush=True)
 for name in ['compare_macd.py','compare_head_shoulders.py']:
  r=subprocess.run([sys.executable,str(folder/name)],capture_output=True,text=True)
  if r.returncode:raise RuntimeError(r.stderr)
 merged={}
 for filename in ['macd_comparison.json','head_shoulders.json']:
  d=json.loads((folder/filename).read_text())
  for k,v in d['models'].items():merged[k]={s:{a:b for a,b in x.items() if a!='events'} for s,x in v.items()}
 summary={'symbol':sym.upper(),'source_path':'artifacts/issue16/data/'+sym+'_1m.csv.gz','bars':len(rows),'input_sha256':hashlib.sha256((folder/'spx.csv').read_bytes()).hexdigest(),'status':'ARCHIVE_TRAINING_ONLY_NOT_SPX','models':merged}
 (folder/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)
