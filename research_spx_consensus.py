"""Fixed single consensus hypothesis; consumed-session diagnostic only."""
import argparse
import json
from pathlib import Path
import pandas as pd
from evaluate_spx_extension import load_history
from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_inside_range import _eligible, _wick_onset
from spx_consensus import MODELS, VERSION, features, schedule


def run(source,protocol):
    bars,_,digest,_=load_history(source)
    groups={day:group.copy() for day,group in bars.groupby(bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d'),sort=True)}
    boundary=pd.Timestamp('2026-10-22T17:30Z');day22=groups['2026-10-22']
    slices=[('oct22_head',day22.loc[day22.index<boundary].copy(),None),
            ('oct22_tail',day22,boundary),('oct21',groups['2026-10-21'],None),
            ('oct20_partial',groups['2026-10-20'],None)]
    reports=[]
    for name,segment,start in slices:
        segment.attrs.update(symbol='SPX',security_type='IND')
        frame=features(segment);eligible=_eligible(segment,frame,start)
        events=_wick_onset(segment,movement_events(segment,frame,eligible,ResearchConfig()))
        models={}
        for model in MODELS:
            rows=schedule(frame,model)
            if start is not None:
                rows=[x for x in rows if segment.index[x['index']]>=start]
            scored=[x for x in rows if x['index'] in eligible]
            metrics={};matches={}
            for delay in (0,1,2):
                matched=[dict(x) for x in scored]
                metrics[str(delay)]=score_signals(events,matched,segment,eligible,'rth',ResearchConfig(),
                    bootstrap=False,availability_delay_minutes=delay)
                matches[str(delay)]=matched
            models[model]=dict(candidates=len(rows),censored=len(rows)-len(scored),metrics=metrics,matches=matches)
        checks=[];full=schedule(frame,'inside_slope_consensus')
        for count in (60,120,240):
            if count>=len(segment):continue
            partial=segment.iloc[:count].copy();partial.attrs.update(segment.attrs)
            changed=segment.copy();changed.iloc[count:]+=1000
            expected=[x for x in full if x['index']<count]
            checks.append(dict(cutoff=count,prefix=schedule(features(partial),'inside_slope_consensus')==expected,
                future_poison=[x for x in schedule(features(changed),'inside_slope_consensus') if x['index']<count]==expected))
        reports.append(dict(name=name,events=len(events),models=models,causality=checks))
    if [x['events'] for x in reports]!=[16,12,22,12]:raise ValueError('event_universe_drift')
    if not all(c['prefix'] and c['future_poison'] for x in reports for c in x['causality']):raise ValueError('causality_failed')
    return dict(mode='CONSUMED_CONSENSUS_DIAGNOSTIC',protocol_commit=protocol,input_sha256=digest,
        version=VERSION,segments=reports,readiness='NOT_READY',accepted=False,model_selected=None,
        independent_validation=False,notifications_enabled=False,orders_enabled=False,
        limitations=['All dates consumed before this hypothesis; no independent evidence.',
                    'No options P&L, measured arrival latency or production activation.'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--protocol-commit',required=True);args=parser.parse_args()
    result=run(args.input,args.protocol_commit)
    path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2,allow_nan=False)
    for segment in result['segments']:
        print(segment['name'],'events',segment['events'])
        for model,row in segment['models'].items():
            m=row['metrics']['0']
            print(model,{k:m[k] for k in ('signals','matched_events','early_matched_events','false_alarms','median_lead_minutes')})
    print('NOT_READY')
