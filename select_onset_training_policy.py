"""Bounded forward-only selection within consumed training, never live code."""
import argparse
import json
import hashlib
from pathlib import Path
import pandas as pd
from intrabar_compression import minute_frame
from linear_onset_forecast import feature_matrix,training_labels,fit,warnings
from compare_amd_reclaim import rolling_features,f1
from hunter_research import ResearchConfig,eligible_indices,score_signals


def select(path,output,protocol_commit):
    source=hashlib.sha256(path.read_bytes()).hexdigest()
    if source!='5704e0a957c7d0b8a6e67902304a7cc15ec4ddb0c5e99d6a51821630a8886346':raise ValueError('unregistered_source')
    raw=pd.read_csv(path,index_col=0,parse_dates=True)
    # Truncate BEFORE feature calculation and selection: later six days cannot
    # influence even a reduction or an accidentally noncausal helper.
    raw=raw[raw.index<pd.Timestamp('2026-09-05T00:00Z')]
    minute=minute_frame(raw);features=feature_matrix(minute);base=rolling_features(minute)
    dates=minute.index.tz_convert('America/New_York').strftime('%Y-%m-%d');days=sorted(set(dates))
    if days!=['2026-09-01','2026-09-02','2026-09-03','2026-09-04']:raise ValueError('unregistered_train_days')
    indices=[]
    for day in days:
        expected=pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        rows=[i for i,t in enumerate(minute.index) if t in expected];indices+=rows[10:-10]
    config=ResearchConfig();eligible=set(eligible_indices(minute,base,indices,config))
    # Original retained event indices agree because training is a prefix.
    all_events=pd.read_csv('artifacts/intrabar_development_result/events_fine.csv').to_dict('records')
    events=[e for e in all_events if int(e['end_index'])<len(minute)]
    policies={(strength,threshold):[] for strength in (.01,.1,1.) for threshold in (.35,.5,.65)}
    validation_indices=[];validation_events=[];folds=[]
    for end in (2,3):
        train=[i for i in indices if dates[i] in days[:end] and i in eligible and features.valid.iloc[i]]
        train_events=[e for e in events if dates[int(e['anchor_index'])] in days[:end]]
        labels,keep=training_labels(minute,train,train_events)
        decisions=[i for i in indices if dates[i]==days[end]];observable=[i for i in decisions if i in eligible]
        validation_indices+=observable
        validation_events += [e for e in events if int(e['anchor_index']) in set(observable)]
        folds.append(dict(train_days=days[:end],next_day=days[end],training_rows=len(train)))
        for strength in (.01,.1,1.):
            model=fit(features,train,labels,keep,strength)
            for threshold in (.35,.5,.65):
                policy=dict(model,threshold=threshold)
                policies[(strength,threshold)]+=[s for s in warnings(minute,features,policy,decisions) if s['index'] in set(observable)]
    ranking=[]
    for (strength,threshold),signals in policies.items():
        m=score_signals(validation_events,signals,minute,validation_indices,'rth',config,bootstrap=False)
        supported=bool(m['signals']>=3 and m['precision']>=.5 and m['median_lead_minutes'] is not None and
            m['median_lead_minutes']>=1 and m['false_alarms_per_session']<=2)
        ranking.append(dict(regularization=strength,threshold=threshold,admissible=supported,early_f1=f1(m),metrics=m))
    supported=[r for r in ranking if r['admissible']]
    supported.sort(key=lambda r:(-r['early_f1'],r['metrics']['false_alarms'],-r['regularization'],-r['threshold']))
    report=dict(usage='CONSUMED_TRAIN_ONLY_FORWARD_SELECTION',input_sha256=source,protocol_commit=protocol_commit,
        protocol_sha256=hashlib.sha256(Path('docs/ONSET_TRAIN_POLICY_PROTOCOL.md').read_bytes()).hexdigest(),
        selection_days=days,folds=folds,ranking=ranking,selected=supported[0] if supported else None,
        accepted=False,readiness='NOT_READY',later_six_days_used=False)
    output.mkdir(parents=True,exist_ok=True)
    if supported:
        train=[i for i in indices if i in eligible and features.valid.iloc[i]];labels,keep=training_labels(minute,train,events)
        model=fit(features,train,labels,keep,supported[0]['regularization']);model['threshold']=supported[0]['threshold']
        (output/'selected_model.json').write_text(json.dumps(model,indent=2),encoding='utf-8')
    (output/'selection.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps(dict(selected=report['selected'],policies=[dict(l2=r['regularization'],threshold=r['threshold'],
        signals=r['metrics']['signals'],early=r['metrics']['early_matched_events'],precision=r['metrics']['precision'],
        median_lead=r['metrics']['median_lead_minutes'],false_per_session=r['metrics']['false_alarms_per_session']) for r in ranking])),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--protocol-commit',required=True);a=p.parse_args();select(a.input,a.output,a.protocol_commit)
