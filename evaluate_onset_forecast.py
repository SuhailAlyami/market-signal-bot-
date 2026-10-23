"""One frozen train/development-validation comparison; never call it holdout."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from intrabar_compression import minute_frame
from compare_amd_reclaim import rolling_features,f1
from hunter_research import ResearchConfig,eligible_indices,score_signals
from validate_independent_reversal import absolute_gate,paired_interval
from linear_onset_forecast import feature_matrix,training_labels,fit,warnings,VERSION


def evaluate(path,output,protocol_commit):
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!='5704e0a957c7d0b8a6e67902304a7cc15ec4ddb0c5e99d6a51821630a8886346':raise ValueError('unregistered_source')
    baseline_path=Path('artifacts/compression_episode_development')
    baseline_report=json.loads((baseline_path/'report.json').read_text())
    if baseline_report['input_sha256']!=digest:raise ValueError('baseline_source_mismatch')
    raw=pd.read_csv(path,index_col=0,parse_dates=True).astype(float);minute=minute_frame(raw)
    f=feature_matrix(minute);base=rolling_features(minute);config=ResearchConfig()
    events=pd.read_csv('artifacts/intrabar_development_result/events_fine.csv').to_dict('records')
    baseline=pd.read_csv(baseline_path/'released_baseline_setup_signals.csv').to_dict('records')
    local=minute.index.tz_convert('America/New_York');days=sorted(set(local.strftime('%Y-%m-%d')))
    if days!=['2026-09-01','2026-09-02','2026-09-03','2026-09-04','2026-09-08','2026-09-09','2026-09-10','2026-09-11','2026-09-14','2026-09-15']:
        raise ValueError('unregistered_development_dates')
    indices=[];coverage=[]
    for day in days:
        expected=pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        positions=[i for i,t in enumerate(minute.index) if t in expected];indices+=positions[10:-10]
        data=minute.loc[minute.index.isin(expected)]
        coverage.append(dict(day=day,complete=bool(data.index.equals(expected) and data.notna().all().all() and data.Volume.gt(0).all())))
    if not all(c['complete'] for c in coverage):raise ValueError('incomplete_registered_source')
    eligible=set(eligible_indices(minute,base,indices,config));dates=local.strftime('%Y-%m-%d')
    train=[i for i in indices if dates[i] in days[:4] and i in eligible and f.valid.iloc[i]]
    train_events=[e for e in events if dates[int(e['anchor_index'])] in days[:4]]
    labels,keep=training_labels(minute,train,train_events)
    output.mkdir(parents=True,exist_ok=True)
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),mode='CONSUMED_DEVELOPMENT_CHRONOLOGICAL_VALIDATION',
        rule_version=VERSION,protocol_commit=protocol_commit,
        protocol_sha256=hashlib.sha256(Path('docs/LINEAR_ONSET_FORECAST_PROTOCOL.md').read_bytes()).hexdigest(),
        input_sha256=digest,train_days=days[:4],validation_days=days[4:],coverage=coverage,
        training_class_counts=np.bincount(labels[keep],minlength=3).tolist(),ambiguous_training_rows=int((~keep).sum()),
        independent=False,accepted=False,readiness='NOT_READY',results={})
    try:model=fit(f,train,labels,keep)
    except ValueError as exc:
        report.update(blocker=str(exc),development_qualified=False)
        (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True);return report
    (output/'model.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    report['model_sha256']=hashlib.sha256((output/'model.json').read_bytes()).hexdigest()
    for phase,phase_days in [('train',days[:4]),('development_validation',days[4:])]:
        decisions=[i for i in indices if dates[i] in phase_days]
        observable=[i for i in decisions if i in eligible];allowed=set(observable)
        phase_events=[e for e in events if int(e['anchor_index']) in allowed]
        predicted=warnings(minute,f,model,decisions)
        report['results'][phase]={}
        for delay in (0,1):
            report['results'][phase][str(delay)]={}
            for name,signals in [('forecast',predicted),('released_setup',baseline)]:
                selected=[dict(s) for s in signals if s['index'] in allowed]
                metrics=score_signals(phase_events,selected,minute,observable,'rth',config,
                    bootstrap=False,availability_delay_minutes=delay)
                metrics.update(early_f1=f1(metrics),absolute_gate=absolute_gate(metrics))
                report['results'][phase][str(delay)][name]=metrics
                if not delay:
                    columns=list(selected[0]) if selected else ['index','direction','bar_time','detected_at','event_id','lead_minutes']
                    pd.DataFrame(selected,columns=columns).to_csv(output/f'{phase}_{name}_signals.csv',index=False)
    result=report['results']['development_validation'];new=result['0']['forecast'];old=result['0']['released_setup']
    report['paired_interval']=paired_interval(old,new)
    report['stress_gain']=result['1']['forecast']['early_f1']-result['1']['released_setup']['early_f1']
    report['development_qualified']=bool(absolute_gate(new) and report['paired_interval'][0]>0 and report['stress_gain']>=0)
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(training_class_counts=report['training_class_counts'],development_qualified=report['development_qualified'],
        metrics={k:{name:value[name] for name in ('signals','precision','early_matched_events','early_event_recall','median_lead_minutes','false_alarms_per_session')}
        for k,value in result['0'].items()},paired=report['paired_interval'])),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol-commit',required=True);a=p.parse_args();evaluate(a.input,a.output,a.protocol_commit)
