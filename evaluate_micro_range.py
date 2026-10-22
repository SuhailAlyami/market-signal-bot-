"""Development diagnosis then one protected unseen-period test of fixed rules."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from hunter_research import ResearchConfig,validate_bars,eligible_indices,movement_events,score_signals
from validate_independent_reversal import replay,absolute_gate,paired_interval
from compare_amd_reclaim import f1
from micro_range_model import features,candidate,VERSION

ROOT=Path(__file__).resolve().parent
CONSUMED_NATIVE_SHA='bb2f5c0d7d4e1da4e2f68d3c4717515d5c9a6f760d6cc61b9e566bf2d21bb0e4'


def check_independence(mode,metadata,locked):
    if mode=='independent':
        if metadata['input_sha256']==CONSUMED_NATIVE_SHA or metadata['requested_dates']!=locked:
            raise ValueError('consumed_or_unregistered_test_data')
        if not metadata.get('protocol_commit'):raise ValueError('missing_preregistered_protocol_commit')


def evaluate(directory,output,mode):
    meta=json.loads((directory/'acquisition.json').read_text(encoding='utf-8'))
    if meta['status']!='acquired':raise ValueError('acquisition_not_complete')
    locked=json.loads((ROOT/'docs/micro_range_locked_dates.json').read_text())
    check_independence(mode,meta,locked)
    path=directory/'native_es_1m.csv.gz'
    if hashlib.sha256(path.read_bytes()).hexdigest()!=meta['input_sha256']:raise ValueError('source_hash_changed')
    raw=validate_bars(pd.read_csv(path,index_col=0,parse_dates=True))
    local=raw.index.tz_convert('America/New_York');minute=local.hour*60+local.minute
    bars=raw[(minute>=570)&(minute<960)];f=features(bars);config=ResearchConfig()
    dates=meta['requested_dates'];coverage=[];indices=[]
    for day in dates:
        expected=pd.date_range(day+' 09:30',periods=390,freq='min',tz='America/New_York').tz_convert('UTC')
        daybars=bars[bars.index.isin(expected)]
        good=(np.isfinite(daybars).all(axis=1)&(daybars.Volume>0)&(daybars.Low>0)&
            (daybars.High>=daybars[['Open','Close','Low']].max(axis=1))&
            (daybars.Low<=daybars[['Open','Close']].min(axis=1)))
        coverage.append(dict(day=day,rows=len(daybars),valid_rows=int(good.sum()),
            complete=bool(daybars.index.equals(expected) and good.all())))
        positions=np.flatnonzero(bars.index.isin(expected)).tolist();indices.extend(positions[10:-10])
    print('Evaluating fixed model: '+mode,flush=True)
    plans,diagnostics=replay(bars,f,alternative=candidate)
    plans['micro_range']=plans.pop('reversal');diagnostics['micro_range']=diagnostics.pop('reversal')
    eligible=eligible_indices(bars,f,indices,config);observable=set(eligible);allowed=set(indices)
    events=movement_events(bars,f,eligible,config);results={}
    output.mkdir(parents=True,exist_ok=True);pd.DataFrame(events).to_csv(output/'events.csv',index=False)
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
                output/f'{model}_delay{delay}.csv',index=False)
    old,new=results['0']['continuation'],results['0']['micro_range'];interval=paired_interval(old,new)
    stress=results['1']['micro_range']['early_f1']-results['1']['continuation']['early_f1']
    accept=bool(mode=='independent' and all(d['complete'] for d in coverage) and
        absolute_gate(new) and interval[0]>0 and stress>=0)
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),mode=mode,model=VERSION,
        input_sha256=meta['input_sha256'],protocol_commit=meta['protocol_commit'],source_contract=meta['contract'],
        coverage=coverage,results=results,diagnostics=diagnostics,paired_interval=interval,
        stress_f1_difference=stress,accepted=accept,readiness='ACCEPTED_UNDERLYING_ONLY' if accept else 'NOT_READY',
        development_promising=bool(new['early_f1']>old['early_f1']),parameters_searched=False)
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'mode':mode,'accepted':accept,'development_promising':report['development_promising'],
        'diagnostics':diagnostics,'paired':interval,'current':{k:old[k] for k in ('events','signals','precision','early_event_recall','early_f1','median_lead_minutes')},
        'micro_range':{k:new[k] for k in ('events','signals','precision','early_event_recall','early_f1','median_lead_minutes')}}),flush=True)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--mode',choices=['development','independent'],required=True)
    args=parser.parse_args();evaluate(args.directory,args.output,args.mode)
