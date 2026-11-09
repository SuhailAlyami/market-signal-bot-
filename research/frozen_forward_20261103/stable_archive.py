"""Append closed historical bars; preserve first observations and reject revisions."""
import json,math,os
from pathlib import Path
import pandas as pd
FIELDS=['open','high','low','close','volume']

def rows(raw,asof):
 if raw.get('chart_step')!=300:raise ValueError('expected native5min bars')
 n=len(raw['time'])
 if any(len(raw[k])!=n for k in FIELDS if k in raw):raise ValueError('array length mismatch')
 ts=pd.to_datetime(raw['time'],utc=True)
 if ts.duplicated().any() or not ts.is_monotonic_increasing:raise ValueError('duplicate or unsorted input')
 out={};forming=0
 for i,t in enumerate(ts):
  if t+pd.Timedelta(minutes=5)>asof:forming+=1;continue
  r={k:(raw[k][i] if k in raw else None) for k in FIELDS}
  if not all(math.isfinite(float(x)) for x in r.values() if x is not None) or min(float(r[k]) for k in ['open','high','low','close'])<=0:raise ValueError('invalid closed price')
  if r['low']>min(r['open'],r['close']) or r['high']<max(r['open'],r['close']) or (r['volume'] is not None and r['volume']<0):raise ValueError('inconsistent closed OHLCV')
  out[str(t)]=r
 return out,forming

def merge_archive(snapshot,archive,asof):
 asof=pd.Timestamp(asof)
 if asof.tzinfo is None:raise ValueError('asof timezone required')
 incoming=json.loads(Path(snapshot).read_text());new,forming=rows(incoming,asof);archive=Path(archive)
 old={}
 if archive.exists():
  raw=json.loads(archive.read_text());archive_end=pd.to_datetime(raw['time'],utc=True).max()+pd.Timedelta(minutes=5) if raw['time'] else asof;old,_=rows(raw,archive_end)
 if old:
  latest=max(pd.Timestamp(t) for t in old);backfill=[t for t in new if t not in old and pd.Timestamp(t)<=latest]
  if backfill:raise ValueError('historical backfill would alter prior feature history; archive unchanged')
 conflicts=[]
 for t in old.keys()&new.keys():
  if any((old[t][k]!=new[t][k]) if old[t][k] is None or new[t][k] is None else not math.isclose(float(old[t][k]),float(new[t][k]),rel_tol=0,abs_tol=1e-9) for k in FIELDS):conflicts.append(t)
 if conflicts:raise ValueError('closed-bar revision detected; archive unchanged: '+','.join(sorted(conflicts)[:5]))
 combined=dict(old);combined.update({t:r for t,r in new.items() if t not in old});keys=sorted(combined,key=pd.Timestamp);result={k:v for k,v in incoming.items() if k not in ['time']+FIELDS};result['time']=[pd.Timestamp(t).isoformat().replace('+00:00','Z') for t in keys]
 for k in FIELDS:
  if k=='volume' and all(combined[t][k] is None for t in keys):continue
  result[k]=[combined[t][k] for t in keys]
 if keys:result['chart_start']=result['time'][0];result['chart_end']=(pd.Timestamp(keys[-1])+pd.Timedelta(minutes=5)).isoformat().replace('+00:00','Z')
 tmp=archive.with_suffix(archive.suffix+'.tmp');tmp.write_text(json.dumps(result));os.replace(tmp,archive)
 return {'old_bars':len(old),'incoming_closed_bars':len(new),'newly_preserved_bars':len(combined)-len(old),'forming_bars_excluded':forming,'archive_bars':len(combined),'revision_policy':'reject_and_preserve_existing'}
