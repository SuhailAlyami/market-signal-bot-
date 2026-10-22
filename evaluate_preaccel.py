"""Frozen WATCH versus original SETUP, with entry confirmations scored separately."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from preaccel_warning import detect,VERSION
from intrabar_compression import refine_events
from compare_amd_reclaim import MemoryRuntime,rolling_features,baseline_candidate,f1
from hunter_research import ResearchConfig,eligible_indices,movement_events,score_signals
from validate_independent_reversal import absolute_gate,paired_interval
from hunter_runtime import futures_active


def evaluate(path,output,protocol_commit):
    raw=pd.read_csv(path,index_col=0,parse_dates=True).astype(float)
    minute,warnings,entries,diagnostics=detect(raw)
    features=rolling_features(minute);fs=[f for _,f in features.iterrows()]
    runtime=MemoryRuntime(lambda data,i:baseline_candidate(fs[i]));setups=[]
    with patch('price_action_context.observe',return_value={'status':'research_skipped'}):
        for i,start in enumerate(minute.index):
            end=start+pd.Timedelta(minutes=1)
            if not fs[i]['valid'] or not futures_active(end.to_pydatetime()):
                runtime._cancel('ES=F',end.to_pydatetime(),{'last_completed_bar':end.isoformat()},'invalid_or_closed');continue
            for event in runtime._process_bar('ES=F',minute,i,end.to_pydatetime()):
                if event['state']=='SETUP':setups.append(dict(index=i,direction=1 if event['direction']=='UP' else -1,
                    bar_time=start.isoformat(),detected_at=end.isoformat()))
    local=minute.index.tz_convert('America/New_York');indices=[];coverage=[]
    for day in sorted(set(local.date)):
        expected=pd.date_range(str(day)+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        positions=[i for i,t in enumerate(minute.index) if t in expected];indices.extend(positions[10:-10])
        data=minute.loc[minute.index.isin(expected)]
        coverage.append(dict(day=str(day),complete=bool(data.index.equals(expected) and data.notna().all().all() and data.Volume.gt(0).all())))
    config=ResearchConfig();eligible=eligible_indices(minute,features,indices,config);allowed=set(indices);observable=set(eligible)
    events=refine_events(movement_events(minute,features,eligible,config),minute,raw)
    output.mkdir(parents=True,exist_ok=True);results={}
    for delay in (0,1):
        results[str(delay)]={}
        for name,signals in (('baseline_setup',setups),('watch',warnings),('entry',entries)):
            selected=[dict(s) for s in signals if s['index'] in allowed and s['index'] in observable]
            metric=score_signals(events,selected,minute,eligible,'rth',config,bootstrap=False,availability_delay_minutes=delay)
            metric.update(early_f1=f1(metric),absolute_gate=absolute_gate(metric));results[str(delay)][name]=metric
            if not delay:pd.DataFrame(selected).to_csv(output/f'{name}_signals.csv',index=False)
    old=results['0']['baseline_setup'];new=results['0']['watch'];interval=paired_interval(old,new)
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),mode='DEVELOPMENT_CONSUMED_NOT_INDEPENDENT',
        rule_version=VERSION,protocol_commit=protocol_commit,protocol_sha256=hashlib.sha256(Path('docs/PREACCEL_WARNING_PROTOCOL.md').read_bytes()).hexdigest(),
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),events=len(events),coverage=coverage,diagnostics=diagnostics,
        results=results,paired_early_f1_interval=interval,accepted=False,readiness='NOT_READY',
        development_qualified=bool(absolute_gate(new) and all(c['complete'] for c in coverage) and interval[0]>0 and
            results['1']['watch']['early_f1']>=results['1']['baseline_setup']['early_f1']))
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(diagnostics=diagnostics,events=len(events),development_qualified=report['development_qualified'],
        metrics={name:{k:m[k] for k in ('signals','precision','early_matched_events','early_event_recall','median_lead_minutes','false_alarms_per_session')}
        for name,m in results['0'].items()},paired=interval)),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol-commit',required=True);a=p.parse_args();evaluate(a.input,a.output,a.protocol_commit)
