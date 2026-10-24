"""Diagnostic native-SPX replay. No options, live delivery or holdout claims."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from hunter_research import ResearchConfig, movement_events, score_signals
from spx_price_watch import observe, VERSION
from spx_price_runtime import SPXPriceRuntime


def replay(path, output, protocol_commit):
    raw_bytes=Path(path).read_bytes();payload=json.loads(raw_bytes)
    h=payload['history'];received=pd.Timestamp(payload['received_at'])
    root=payload['contract']
    if (root.get('symbol')!='SPX' or root.get('country_code')!='US'
            or not any(s.get('security_type')=='IND' for s in root.get('sections',[]))):
        raise ValueError('native_spx_identity_required')
    names=('time','open','high','low','close')
    if h.get('error') or any(not isinstance(h.get(k),list) for k in names):
        raise ValueError('invalid_history')
    if len({len(h[k]) for k in names})!=1 or not h['time']:
        raise ValueError('invalid_arrays')
    if received.tz is None or any(pd.Timestamp(t).tz is None for t in h['time']):
        raise ValueError('aware_source_clock_required')
    times=pd.to_datetime(h['time'],utc=True)
    if not times.is_unique or not times.is_monotonic_increasing:
        raise ValueError('unordered_history')
    # The provider can return the requested session end, later than receipt.
    # That cannot make an unfinished received bar complete.
    cutoff=min(received,pd.Timestamp(h['chart_end']))
    data=pd.DataFrame({k:h[k.lower()] for k in ('Open','High','Low','Close')},index=times)
    partial=int((data.index+pd.Timedelta(minutes=1)>cutoff).sum())
    data=data.loc[data.index+pd.Timedelta(minutes=1)<=cutoff]
    data.attrs.update(symbol='SPX',security_type='IND',source='IBKR_CONNECTED_TOOLS_HISTORY',
                      live_feed_verified=False)
    observations=[observe(data,i) for i in range(len(data))]
    atr=pd.DataFrame({'atr':[r.get('prior_atr',np.nan) for r in observations]},index=data.index)
    config=ResearchConfig();eligible=[]
    for i in range(len(data)-config.horizon):
        future=data.iloc[i+1:i+config.horizon+1]
        if (observations[i].get('prior_atr',0)>0
                and data.index[i+config.horizon]-data.index[i]==pd.Timedelta(minutes=config.horizon)
                and np.isfinite(future.to_numpy()).all()
                and (future>0).all().all()
                and (future.High>=future[['Open','Low','Close']].max(axis=1)).all()
                and (future.Low<=future[['Open','Close']].min(axis=1)).all()):
            eligible.append(i)
    events=movement_events(data,atr,eligible,config)
    for event in events:
        i,side=event['anchor_index'],event['direction']
        threshold=data.Close.iloc[i]+side*config.onset_fraction*event['target_points']
        future=data.iloc[i+1:event['target_index']+1]
        hits=np.flatnonzero((future.High>=threshold if side>0 else future.Low<=threshold).to_numpy())
        event['onset_time']=data.index[i+1+int(hits[0])].isoformat()
    candidates=[];confirmations=[];dispositions=[]
    with tempfile.TemporaryDirectory() as directory:
        runtime=SPXPriceRuntime(Path(directory)/'state.json',Path(directory)/'journal.jsonl')
        for i in range(len(data)):
            if i<30:continue
            end=data.index[i]+pd.Timedelta(minutes=1)
            if not runtime.market_is_open(end.to_pydatetime()):continue
            for event in runtime._process_bar('SPX',data,i,end.to_pydatetime()):
                signal={'index':i,'direction':1 if event['direction']=='UP' else -1,
                        'detected_at':end.isoformat(),'pattern':event['pattern']}
                if event['state']=='SETUP':candidates.append(signal)
                elif event['state']=='TRIGGER':confirmations.append(signal)
        dispositions=[json.loads(line) for line in (Path(directory)/'journal.jsonl').read_text(encoding='utf-8').splitlines()
                      if json.loads(line).get('record_type')=='candidate_disposition']
    metrics={};allowed=set(eligible)
    for name,signals in [('watch',candidates),('confirmation',confirmations)]:
        scored=[dict(s) for s in signals if s['index'] in allowed]
        metric=score_signals(events,scored,data,eligible,'rth',config,bootstrap=False)
        metric['early_false_alarms_per_session']=(metric['signals']-metric['early_matched_events'])/metric['sessions'] if metric['sessions'] else None
        metric['early_missed_events']=metric['events']-metric['early_matched_events']
        metric['candidate_signals_total']=len(signals)
        metric['censored_signals']=len(signals)-len(scored)
        metrics[name]=metric
    report={'rule_version':VERSION,'protocol_commit':protocol_commit,
            'input_sha256':hashlib.sha256(raw_bytes).hexdigest(),
            'mode':'CONSUMED_PARTIAL_SESSION_DEVELOPMENT_DIAGNOSTIC',
            'source':'IBKR native SPX IND historical prices; live status unverified',
            'source_contract_id':root['underlying_contract_id'],
            'provider_chart_end':h['chart_end'],'received_at':received.isoformat(),
            'completion_cutoff':cutoff.isoformat(),'excluded_partial_bars':partial,
            'bars':len(data),'first':data.index[0].isoformat(),'last':data.index[-1].isoformat(),
            'first_eligible_decision':(data.index[eligible[0]]+pd.Timedelta(minutes=1)).isoformat() if eligible else None,
            'onset_semantics':'START of first minute whose high/low touches 25% target; conservative, intraminute path unknown',
            'baseline_comparison':'not performed: original SPX model requires missing ES observations',
            'reason_counts':dict(Counter(r['reason'] for r in observations)),
            'candidate_disposition_counts':dict(Counter(r['reason'] for r in dispositions)),
            'candidate_dispositions':dispositions,
            'delivery_blocker':'research_notifications_disabled',
            'metrics':metrics,'watch':candidates,'confirmations':confirmations,'events':events,
            'readiness':'NOT_READY','accepted':False,'notifications_enabled':False,
            'orders_enabled':False,'holdout':False}
    Path(output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True);p.add_argument('--output',required=True)
    p.add_argument('--protocol-commit',required=True);a=p.parse_args()
    r=replay(a.input,a.output,a.protocol_commit)
    print(json.dumps({k:r[k] for k in ('bars','events','first_eligible_decision','metrics','readiness')},allow_nan=False))
