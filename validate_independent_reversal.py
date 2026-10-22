"""One locked out-of-development test. No tuning, live imports or notifications."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from acquire_independent_history import DATES
from compare_amd_reclaim import MemoryRuntime, rolling_features, baseline_candidate, f1
from hunter_research import ResearchConfig,eligible_indices,movement_events,score_signals,validate_bars
from hunter_runtime import futures_active
from independent_strategy_models import continuation_confirmation,reversal_candidate,common_risk_plan


def absolute_gate(m):
    ci=m['precision_wilson_95']
    return bool(m['sessions']>=5 and m['signals']>=30 and m['precision'] is not None and
        m['precision']>=.50 and ci and ci[0]>=.40 and m['early_event_recall'] is not None and
        m['early_event_recall']>=.20 and m['false_alarms_per_session']<=2 and
        m['median_lead_minutes'] is not None and m['median_lead_minutes']>=1)


def paired_interval(old,new,draws=5000):
    days=sorted(set(old['session_counts']) & set(new['session_counts']))
    if not days:return [0.,0.]
    rng=np.random.default_rng(20261022);differences=[]
    for _ in range(draws):
        selected=[days[i] for i in rng.integers(0,len(days),len(days))]
        scores=[]
        for metrics in (old,new):
            rows=[metrics['session_counts'][d] for d in selected]
            denominator=sum(r['signals']+r['events'] for r in rows)
            scores.append(2*sum(r['early'] for r in rows)/denominator if denominator else 0.)
        differences.append(scores[1]-scores[0])
    return [float(v) for v in np.quantile(differences,[.025,.975])]


def replay(bars,features):
    fs=[f for _,f in features.iterrows()]
    runtime=MemoryRuntime(lambda data,i:baseline_candidate(fs[i]))
    plans={'continuation':[],'reversal':[]};diagnostics={m:Counter() for m in plans}
    active=None;cooldown=None;previous=None
    with patch('price_action_context.observe',return_value={'status':'replay_skipped'}):
        for i,(start,row) in enumerate(bars.iterrows()):
            end=start+pd.Timedelta(minutes=1);now=end.to_pydatetime();f=fs[i]
            if not f['valid'] or not futures_active(now):
                runtime._cancel('ES=F',now,{'last_completed_bar':end.isoformat()},'invalid_or_closed')
                if active:active=None;cooldown=end+pd.Timedelta(minutes=5)
                previous=row;continue
            for event in runtime._process_bar('ES=F',bars,i,now):
                if event['state']!='TRIGGER':continue
                diagnostics['continuation']['triggers']+=1
                side=1 if event['direction']=='UP' else -1
                if not continuation_confirmation(f,side):
                    diagnostics['continuation']['strategy_rejected']+=1;continue
                plan,reason=common_risk_plan(event,f)
                if plan:plans['continuation'].append(dict(index=i,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat()))
                else:diagnostics['continuation'][reason]+=1
            if active:
                if active['direction']*(row.Close-active['invalidation'])<=0 or end-active['started']>=pd.Timedelta(minutes=10):
                    active=None;cooldown=end+pd.Timedelta(minutes=5)
                previous=row;continue
            if cooldown is not None and end<cooldown:previous=row;continue
            found=reversal_candidate(f,row,previous) if previous is not None else None
            if found:
                diagnostics['reversal']['triggers']+=1;active={**found,'started':end}
                event={**found,'direction':'UP' if found['direction']>0 else 'DOWN'}
                plan,reason=common_risk_plan(event,f)
                if plan:plans['reversal'].append(dict(index=i,direction=found['direction'],bar_time=start.isoformat(),detected_at=end.isoformat()))
                else:diagnostics['reversal'][reason]+=1
            previous=row
    for model in plans:diagnostics[model]['complete_plans']=len(plans[model])
    return plans,{m:dict(counts) for m,counts in diagnostics.items()}


def compare(directory):
    acquisition=json.loads((directory/'acquisition.json').read_text(encoding='utf-8'))
    if acquisition['status']!='acquired':raise RuntimeError('acquisition_blocked_no_test_run')
    path=directory/'native_es_1m.csv.gz';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=acquisition['input_sha256']:raise ValueError('input_hash_changed')
    native=validate_bars(pd.read_csv(path,index_col=0,parse_dates=True))
    local=native.index.tz_convert('America/New_York');minute=local.hour*60+local.minute
    bars=native[(minute>=570)&(minute<960)]
    if bars.empty or bars.index.max()>=pd.Timestamp('2026-09-21T00:00Z'):
        raise ValueError('test_overlaps_development_or_empty')
    coverage=[];indices=[];features=rolling_features(bars);config=ResearchConfig()
    for day in DATES:
        expected=pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        frame=bars[bars.index.isin(expected)]
        good=(np.isfinite(frame).all(axis=1)&(frame.Volume>0)&(frame.Low>0)&
            (frame.High>=frame[['Open','Close','Low']].max(axis=1))&
            (frame.Low<=frame[['Open','Close']].min(axis=1)))
        coverage.append(dict(day=day,rows=len(frame),valid_rows=int(good.sum()),
            complete=bool(frame.index.equals(expected) and good.all())))
        positions=np.flatnonzero(bars.index.isin(expected)).tolist()
        indices.extend(positions[10:-10] if len(positions)>20 else [])
    print('Locked native test loaded; independent dates/coverage checked.',flush=True)
    plans,diagnostics=replay(bars,features)
    eligible=eligible_indices(bars,features,indices,config);observable=set(eligible);allowed=set(indices)
    events=movement_events(bars,features,eligible,config);results={}
    pd.DataFrame(events).to_csv(directory/'events.csv',index=False)
    for delay in (0,1):
        results[str(delay)]={}
        for model,signals in plans.items():
            selected=[dict(s,outcome_observable=s['index'] in observable) for s in signals if s['index'] in allowed]
            scored=[dict(s) for s in selected if s['outcome_observable']]
            metrics=score_signals(events,scored,bars,eligible,'rth',config,bootstrap=True,
                availability_delay_minutes=delay)
            metrics.update(early_f1=f1(metrics),censored=len(selected)-len(scored),absolute_gate=absolute_gate(metrics))
            results[str(delay)][model]=metrics
            pd.DataFrame(selected,columns=['index','direction','bar_time','detected_at','outcome_observable']).to_csv(
                directory/f'{model}_delay{delay}.csv',index=False)
    old,new=results['0']['continuation'],results['0']['reversal']
    interval=paired_interval(old,new)
    stress=results['1']['reversal']['early_f1']-results['1']['continuation']['early_f1']
    complete=all(d['complete'] for d in coverage)
    accept=bool(complete and absolute_gate(new) and interval[0]>0 and stress>=0)
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),input_sha256=acquisition['input_sha256'],
        acquisition_protocol_commit=acquisition['protocol_commit'],source=acquisition['source'],
        source_contract=acquisition['contract'],coverage=coverage,rows=len(bars),results=results,
        diagnostics=diagnostics,paired_early_f1_difference_95=interval,one_minute_stress_f1_difference=stress,
        continuation_ready=bool(complete and absolute_gate(old)),reversal_accepted=accept,
        detection_readiness='ACCEPTED_UNDERLYING_ES_RESEARCH_ONLY' if accept else 'NOT_READY',
        no_live_freshness_or_option_validation=True,parameter_search=False)
    (directory/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'readiness':report['detection_readiness'],'coverage':coverage,'diagnostics':diagnostics,
        'paired_interval':interval,'current':{k:old[k] for k in ('signals','precision','recall','early_event_recall','median_lead_minutes')},
        'reversal':{k:new[k] for k in ('signals','precision','recall','early_event_recall','median_lead_minutes')}}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,default=Path('artifacts/independent_reversal'))
    compare(parser.parse_args().directory)
