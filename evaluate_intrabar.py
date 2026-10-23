"""One fixed intrabar model; conservative fine-onset scoring for BOTH models."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import pandas as pd

from compare_amd_reclaim import rolling_features,f1
from hunter_research import ResearchConfig,eligible_indices,movement_events,score_signals
from validate_independent_reversal import replay,absolute_gate,paired_interval
from intrabar_compression import detect,refine_events,VERSION


def evaluate(path,output,mode,candidate='compression'):
    if candidate in ('sweep','carry'):
        from intrabar_sweep import detect as detector,VERSION as version
        if candidate=='carry':
            base_detector=detector
            detector=lambda data:base_detector(data,carry_sweep=True)
            version='intrabar-sweep-carry-v1'
    else:detector,version=detect,VERSION
    raw=pd.read_csv(path,index_col=0,parse_dates=True).astype(float)
    if mode=='independent':
        locked=json.loads(Path('docs/micro_range_locked_dates.json').read_text())
        observed=sorted(set(raw.index.tz_convert('America/New_York').strftime('%Y-%m-%d')))
        if observed!=locked:raise ValueError('unregistered_or_consumed_test_dates')
        metadata=json.loads((path.parent/'acquisition.json').read_text())
        if metadata.get('input_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest() or not metadata.get('protocol_commit'):
            raise ValueError('missing_or_mismatched_preregistered_source_manifest')
    minute,plans,diagnostics=detector(raw)
    features=rolling_features(minute);config=ResearchConfig()
    current,_=replay(minute,features,alternative=lambda *args:None)
    signals={'continuation':current['continuation'],'intrabar':plans}
    local=minute.index.tz_convert('America/New_York');indices=[];coverage=[]
    for day in sorted(set(local.date)):
        expected=pd.date_range(str(day)+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        positions=[i for i,t in enumerate(minute.index) if t in expected]
        indices.extend(positions[10:-10]);daydata=minute.loc[minute.index.isin(expected)]
        coverage.append(dict(day=str(day),rows=len(daydata),complete=bool(daydata.index.equals(expected) and daydata.notna().all().all() and daydata.Volume.gt(0).all())))
    eligible=eligible_indices(minute,features,indices,config);observable=set(eligible);allowed=set(indices)
    coarse=movement_events(minute,features,eligible,config);fine=refine_events(coarse,minute,raw)
    results={};output.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(fine).to_csv(output/'events_fine.csv',index=False)
    for label,events in (('fine',fine),('coarse',coarse)):
        results[label]={}
        for delay in (0,1):
            results[label][str(delay)]={}
            for model,rows in signals.items():
                selected=[dict(s,outcome_observable=s['index'] in observable) for s in rows if s['index'] in allowed]
                scored=[dict(s) for s in selected if s['outcome_observable']]
                metrics=score_signals(events,scored,minute,eligible,'rth',config,bootstrap=True,
                    availability_delay_minutes=delay)
                metrics.update(early_f1=f1(metrics),censored=len(selected)-len(scored),absolute_gate=absolute_gate(metrics))
                results[label][str(delay)][model]=metrics
                if label=='fine' and delay==0:
                    pd.DataFrame(selected,columns=['index','direction','bar_time','detected_at','outcome_observable']).to_csv(output/f'{model}_signals.csv',index=False)
    old,new=results['fine']['0']['continuation'],results['fine']['0']['intrabar']
    interval=paired_interval(old,new)
    stress=results['fine']['1']['intrabar']['early_f1']-results['fine']['1']['continuation']['early_f1']
    if mode=='independent':
        locked=json.loads(Path('docs/micro_range_locked_dates.json').read_text())
        if [c['day'] for c in coverage]!=locked:raise ValueError('unregistered_or_consumed_test_dates')
    accepted=bool(mode=='independent' and len(fine)==len(coarse) and all(c['complete'] for c in coverage) and absolute_gate(new) and interval[0]>0 and stress>=0)
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),mode=mode,rule_version=version,
        input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),raw_rows=len(raw),minute_rows=len(minute),
        protocol_sha256=hashlib.sha256(Path('docs/INTRABAR_PRESSURE_PROTOCOL.md').read_bytes()).hexdigest(),
        amendment_sha256=hashlib.sha256(Path('docs/INTRABAR_CARRY_PROTOCOL.md' if candidate=='carry' else 'docs/INTRABAR_SWEEP_AMENDMENT.md').read_bytes()).hexdigest() if candidate in ('sweep','carry') else None,
        coverage=coverage,coarse_events=len(coarse),refined_events=len(fine),unrefinable_events=len(coarse)-len(fine),
        results=results,diagnostics=diagnostics,paired_interval=interval,stress_gain=stress,
        development_promising=new['early_f1']>old['early_f1'],accepted=accepted,
        readiness='ACCEPTED_UNDERLYING_ONLY' if accepted else 'NOT_READY')
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'mode':mode,'events':len(fine),'diagnostics':diagnostics,'accepted':accepted,
        'development_promising':report['development_promising'],
        'current':{k:old[k] for k in ('signals','precision','early_matched_events','early_event_recall','median_lead_minutes')},
        'intrabar':{k:new[k] for k in ('signals','precision','early_matched_events','early_event_recall','median_lead_minutes')},
        'paired':interval}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--mode',choices=['development','independent'],required=True)
    parser.add_argument('--candidate',choices=['compression','sweep','carry'],default='compression')
    args=parser.parse_args();evaluate(args.input,args.output,args.mode,args.candidate)
