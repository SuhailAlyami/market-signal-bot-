"""Offline, immutable-model research recorder. Does not place trades or send alerts."""
import argparse,json,hashlib
from pathlib import Path
import numpy as np,pandas as pd
import exchange_calendars as xc
import early_move_eval_openfix as ev
from features import features
P=Path(__file__).resolve().parent

def prepare(d,asof):
 required=['timestamp','open','high','low','close']
 if any(x not in d for x in required):raise ValueError('missing required columns')
 # Refuse naive timestamps instead of silently assuming a timezone.
 if not d.timestamp.astype(str).str.contains(r'(?:Z|[+-]\d\d:\d\d)$',regex=True).all():raise ValueError('timestamps must carry an explicit UTC offset')
 d=d[required].copy();d['ts']=pd.to_datetime(d.pop('timestamp'),utc=True,errors='raise')
 if d.ts.duplicated().any() or not d.ts.is_monotonic_increasing:raise ValueError('timestamps duplicated or not increasing')
 if ((d.ts.dt.second!=0)|(d.ts.dt.microsecond!=0)).any():raise ValueError('not aligned to minute starts')
 for c in ['open','high','low','close']:d[c]=pd.to_numeric(d[c],errors='raise')
 if not np.isfinite(d[['open','high','low','close']]).all().all():raise ValueError('nonfinite OHLC')
 if not ((d.low>0)&(d.low<=d[['open','close']].min(axis=1))&(d.high>=d[['open','close']].max(axis=1))).all():raise ValueError('invalid OHLC')
 asof=pd.Timestamp(asof)
 if asof.tzinfo is None:raise ValueError('asof needs explicit timezone')
 closed=d.ts+pd.Timedelta(minutes=1)<=asof
 if d.empty:return d,{'input':0,'outside_session':0,'not_closed':0,'accepted':0}
 sch=xc.get_calendar('XNYS').schedule.loc[str(d.ts.min().date()):str(d.ts.max().date())];inside=np.zeros(len(d),bool)
 for _,r in sch.iterrows():inside|=((d.ts>=r.open)&(d.ts<r.close)).values
 audit={'input':len(d),'outside_session':int((~inside).sum()),'not_closed':int((~closed).sum()),'accepted':int((inside&closed).sum())}
 return ev.add_atr(ev.add_structure(d.loc[inside&closed].reset_index(drop=True)),'prior20'),audit

def prob(model,X):
 z=((X-np.array(model['mean']))/np.array(model['scale']))@np.array(model['coefficient'])+model['intercept']
 return 1/(1+np.exp(-np.clip(z,-700,700)))

def process(csv,statepath,start,asof,source,consumed=False):
 start=pd.Timestamp(start)
 if start.tzinfo is None:raise ValueError('start needs explicit timezone')
 if start<pd.Timestamp('2026-11-02',tz='UTC') and not consumed:raise ValueError('pre-Nov2 dates are consumed; explicit reproduction flag required')
 if source not in ['IBKR_SPX_IND','FirstRate_SPX_INDEX']:raise ValueError('unsupported source or CFD')
 mb=(P/'MODEL.json').read_bytes();mh=hashlib.sha256(mb).hexdigest();model=json.loads(mb)
 key={'model_sha256':mh,'source':source,'start':str(start),'consumed_reproduction':consumed}
 statepath=Path(statepath)
 state=json.loads(statepath.read_text()) if statepath.exists() else {'identity':key,'last_processed':None,'last_signal':None,'signals':[]}
 if state['identity']!=key:raise ValueError('state identity differs; use a separate recorder file')
 d,audit=prepare(pd.read_csv(csv),asof)
 if d.empty:return state,{'audit':audit,'new_signals':0,'status':'NO_USABLE_DATA'}
 f=features(d)
 if list(f.columns)!=model['feature_order']:raise ValueError('feature order mismatch')
 X=f.values;valid=np.isfinite(X).all(1);tim=np.full(len(d),np.nan);direction=tim.copy();tim[valid]=prob(model['models']['timing'],X[valid]);direction[valid]=prob(model['models']['direction'],X[valid])
 oldprocessed=pd.Timestamp(state['last_processed']) if state['last_processed'] else None
 lastsignal=pd.Timestamp(state['last_signal']) if state['last_signal'] else None;added=0
 for i in np.flatnonzero(valid):
  now=d.ts.iloc[i]+pd.Timedelta(minutes=1)
  if now<start or (oldprocessed is not None and now<=oldprocessed) or tim[i]<model['timing_threshold']:continue
  if lastsignal is not None and (now-lastsignal).total_seconds()<model['cooldown_seconds']:continue
  state['signals'].append({'id':hashlib.sha256((mh+source+str(now)).encode()).hexdigest()[:24],'decision_utc':str(now),'decision_Riyadh':str(now.tz_convert('Asia/Riyadh')),'direction':1 if direction[i]>=.5 else -1,'timing_score_uncalibrated':float(tim[i]),'status':'RESEARCH_ONLY','close_result':'PENDING','next_open_result':'PENDING'});lastsignal=now;added+=1
 lookup={str(t+pd.Timedelta(minutes=1)):i for i,t in enumerate(d.ts)}
 for entry in ['close','next_open']:
  lab=ev.label(d,entry)
  for signal in state['signals']:
   i=lookup.get(signal['decision_utc'])
   if i is None:continue
   status=int(lab['status'][i])
   if status==0:
    name='up_c' if signal['direction']==1 else 'dn_c';signal[entry+'_result']='SUCCESS' if lab[name][i] else 'FAILURE'
   elif status==3:signal[entry+'_result']='UNSCORABLE_GAP'
   elif status in [1,2]:signal[entry+'_result']='UNSCORABLE_WARMUP'
 state['last_processed']=str(max(d.ts.iloc[-1]+pd.Timedelta(minutes=1),oldprocessed) if oldprocessed is not None else d.ts.iloc[-1]+pd.Timedelta(minutes=1));state['last_signal']=str(lastsignal) if lastsignal is not None else None
 state['status']='RESEARCH_ONLY_NOT_READY';state['provenance']='source label supplied by caller; not independently authenticated live data';tmp=statepath.with_suffix(statepath.suffix+'.tmp');tmp.write_text(json.dumps(state,indent=2));tmp.replace(statepath)
 return state,{'audit':audit,'new_signals':added,'total_signals':len(state['signals']),'status':state['status']}

def main():
 a=argparse.ArgumentParser();a.add_argument('csv');a.add_argument('--state',required=True);a.add_argument('--source',required=True,choices=['IBKR_SPX_IND','FirstRate_SPX_INDEX']);a.add_argument('--start',default='2026-11-02T00:00:00Z');a.add_argument('--asof',default=pd.Timestamp.now(tz='UTC').isoformat());a.add_argument('--allow-consumed-reproduction',action='store_true');args=a.parse_args();_,report=process(args.csv,args.state,args.start,args.asof,args.source,args.allow_consumed_reproduction);print(json.dumps(report,indent=2))
if __name__=='__main__':main()
