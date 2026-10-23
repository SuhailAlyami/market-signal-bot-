"""Post-outcome DEVELOPMENT diagnosis, never independent validation or live code."""
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from compare_amd_reclaim import MemoryRuntime,rolling_features,baseline_candidate
from independent_strategy_models import continuation_confirmation,common_risk_plan
from hunter_research import ResearchConfig,eligible_indices,score_signals
from hunter_runtime import futures_active


def diagnose(directory):
    data=pd.read_csv(directory/'native_es_1m.csv.gz',index_col=0,parse_dates=True)
    local=data.index.tz_convert('America/New_York');minute=local.hour*60+local.minute
    bars=data[(minute>=570)&(minute<960)];features=rolling_features(bars)
    events=pd.read_csv(directory/'events.csv').to_dict('records')
    fs=[f for _,f in features.iterrows()]
    runtime=MemoryRuntime(lambda data,i:baseline_candidate(fs[i]))
    trace=[];stages={stage:[] for stage in ('SETUP','TRIGGER','PLAN')}
    with patch('price_action_context.observe',return_value={'status':'diagnosis_skipped'}):
        for i,(start,row) in enumerate(bars.iterrows()):
            f=fs[i];end=start+pd.Timedelta(minutes=1);now=end.to_pydatetime()
            active=runtime.state['symbols'].get('ES=F',{}).get('active',{})
            state=runtime.state['symbols'].get('ES=F',{})
            t=dict(index=i,active_phase=active.get('phase'),active_side=active.get('direction',0),
                cooldown=bool(state.get('cooldown_until') and end<pd.Timestamp(state['cooldown_until'])),
                raw_side=0,setup_side=0,trigger_side=0,plan_side=0,rejection=None)
            if not f['valid'] or not futures_active(now):
                runtime._cancel('ES=F',now,{'last_completed_bar':end.isoformat()},'invalid_or_closed')
                trace.append(t);continue
            raw=baseline_candidate(f);t['raw_side']=raw['direction'] if raw else 0
            for event in runtime._process_bar('ES=F',bars,i,now):
                phase=event['state'];side=1 if event['direction']=='UP' else -1
                if phase not in ('SETUP','TRIGGER'):continue
                t['setup_side' if phase=='SETUP' else 'trigger_side']=side
                signal=dict(index=i,direction=side,bar_time=start.isoformat(),detected_at=end.isoformat())
                stages[phase].append(signal)
                if phase=='TRIGGER':
                    if not continuation_confirmation(f,side):t['rejection']='strategy_filters'
                    else:
                        plan,reason=common_risk_plan(event,f);t['rejection']=reason
                        if plan:t['plan_side']=side;stages['PLAN'].append(dict(signal))
            trace.append(t)
    causes=Counter();rows=[];inside=0;no_early_near=0;no_early_volume=0
    for event in events:
        a,o,target,side=[int(event[k]) for k in ('anchor_index','onset_index','target_index','direction')]
        early=list(range(a,o));window=list(range(a,target))
        actual=any(trace[i]['plan_side']==side for i in early)
        if actual:cause='early_plan'
        elif any(trace[i]['trigger_side']==side for i in early):cause='early_trigger_rejected_by_'+next(trace[i]['rejection'] or 'unknown' for i in early if trace[i]['trigger_side']==side)
        elif any(trace[i]['setup_side']==side or (trace[i]['active_phase']=='SETUP' and trace[i]['active_side']==side) for i in early):
            cause='setup_waits_past_onset'
        elif any(trace[i]['raw_side']==side for i in early):cause='candidate_blocked_by_state_or_cooldown'
        else:cause='no_early_candidate'
        causes[cause]+=1
        near=[i for i in early if 0<=fs[i]['near_high' if side>0 else 'near_low']<=.2]
        no_early_near+=not bool(near)
        no_early_volume+=not any(fs[i]['rvol']>=1.2 for i in early)
        anchor_target=float(bars.Close.iloc[a])+side*float(event['target_points'])
        within=anchor_target<=fs[a]['range_high'] if side>0 else anchor_target>=fs[a]['range_low']
        inside+=int(within)
        trigger_indices=[i for i in window if trace[i]['trigger_side']==side]
        rows.append(dict(event_id=event['event_id'],cause=cause,onset_after_anchor_minutes=o-a,
            target_inside_anchor_20_range=bool(within),early_window_has_near_level=bool(near),
            first_trigger_lag_from_onset=None if not trigger_indices else min(trigger_indices)-o))
    allowed=[]
    for day in sorted(set(bars.index.tz_convert('America/New_York').date)):
        positions=np.flatnonzero(bars.index.tz_convert('America/New_York').date==day).tolist()
        allowed.extend(positions[10:-10])
    eligible=eligible_indices(bars,features,allowed,ResearchConfig());eligible_set=set(eligible)
    stage_metrics={}
    for name,signals in stages.items():
        selected=[dict(s) for s in signals if s['index'] in eligible_set]
        stage_metrics[name]=score_signals(events,selected,bars,eligible,'rth',ResearchConfig(),bootstrap=False)
    report=dict(usage='DEVELOPMENT_CONSUMED_NOT_INDEPENDENT',events=len(events),causes=dict(causes),
        target_inside_prior20_range=inside,no_early_near20_level=no_early_near,
        no_early_volume_confirmation=no_early_volume,
        onset_offset_counts=dict(Counter(r['onset_after_anchor_minutes'] for r in rows)),stage_metrics=stage_metrics)
    out=Path('artifacts/missed_expansion_development');out.mkdir(parents=True,exist_ok=True)
    (out/'diagnosis.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    pd.DataFrame(rows).to_csv(out/'event_causes.csv',index=False)
    print(json.dumps({k:v for k,v in report.items() if k!='stage_metrics'},indent=2))
    for name,m in stage_metrics.items():print(name,{k:m[k] for k in ('signals','matched_events','early_matched_events','precision','early_event_recall','median_lead_minutes')})
    return report


if __name__=='__main__':diagnose(Path('artifacts/independent_reversal'))
