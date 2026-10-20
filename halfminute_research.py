"""Frozen half-minute pressure/release pilot; research only, no execution.

Same canonical minute event targets for all methods. Raw 30-second closes may
supply earlier observations; incomplete minute bars never set prior levels.
One retained historical session cannot validate reliable forecasting.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ibkr_market_data import normalize
from hunter_crossmarket_research import paired_features, signal as cross_rule
from hunter_research import ResearchConfig, _evaluation_context, candidate_signal, wilson

CONFIG={'rvol_half':1.5,'near_atr':.3,'contraction':.55,'setup_move_atr':.1,
        'release_move_atr':.15,'cooldown_seconds':600,'horizon_minutes':10,
        'delays_seconds':[0,15,30,60]}
METHODS=('half_setup','half_release','frozen_minute','baseline_breakout','no_signal')


def complete_minutes(raw):
    if raw.index.tz is None or not raw.index.is_unique or not raw.index.is_monotonic_increasing:
        raise ValueError('aware_unique_ordered_halves_required')
    if not raw.index.equals(raw.index.floor('30s')):
        raise ValueError('halfminute_alignment_required')
    finite=np.isfinite(raw).all(axis=1)
    good=(finite&(raw.Volume>0)&(raw.Low>0)&(raw.High>=raw[['Open','Close','Low']].max(axis=1))&
          (raw.Low<=raw[['Open','Close']].min(axis=1)))
    grouped=raw.groupby(raw.index.floor('min'))
    minute=grouped.agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})
    valid=good.groupby(raw.index.floor('min')).agg(['sum','size'])
    # Exactly both 00s/30s starts, never an incomplete minute or price filling.
    return minute.loc[(valid['sum']==2)&(valid['size']==2)]


def prepared(raw,other):
    minute,companion=complete_minutes(raw),complete_minutes(other)
    f=paired_features(minute,companion)
    otherf=paired_features(companion,minute)
    rolling=raw.Volume.shift(1).rolling(40).median()
    high_level=minute.High.rolling(20).max()
    low_level=minute.Low.rolling(20).min()
    rows=[]
    for i,(stamp,bar) in enumerate(raw.iterrows()):
        previous=stamp.floor('min')-pd.Timedelta(minutes=1)
        end=stamp+pd.Timedelta(seconds=30)
        row={'index':i,'bar_start':stamp,'generated_at':end,'valid':False}
        if previous in f.index and previous in otherf.index and stamp in other.index:
            p,q=f.loc[previous],otherf.loc[previous]
            contiguous=(i>=60 and stamp-raw.index[i-60]==pd.Timedelta(minutes=30))
            own_valid=(contiguous and bool((raw.iloc[i-60:i+1].Volume>0).all()) and
                       bool(np.isfinite(raw.iloc[i-60:i+1]).all().all()))
            own_candles=raw.iloc[i-60:i+1]
            own_valid=own_valid and bool(((own_candles.Low>0)&
                (own_candles.High>=own_candles[['Open','Close','Low']].max(axis=1))&
                (own_candles.Low<=own_candles[['Open','Close']].min(axis=1))).all())
            last_other=other.loc[stamp]
            other_valid=bool(np.isfinite(last_other).all() and last_other.Volume>0 and
                             last_other.Low>0 and last_other.High>=max(last_other.Open,last_other.Close,last_other.Low)
                             and last_other.Low<=min(last_other.Open,last_other.Close))
            if own_valid and other_valid and p.valid and q.valid and rolling.iloc[i]>0:
                row.update(valid=True,close=float(bar.Close),atr=float(p.atr),
                           high_level=float(high_level.loc[previous]),
                           low_level=float(low_level.loc[previous]),
                           contraction=float(p.contraction),trend=float(p.trend_5),
                           move=float((bar.Close-p.close)/p.atr),
                           other_move=float((last_other.Close-q.close)/q.atr),
                           rvol=float(bar.Volume/rolling.iloc[i]))
        rows.append(row)
    return minute,f,rows


def direction(row,method):
    if not row['valid']:return 0
    p=CONFIG
    liquid=row['rvol']>=p['rvol_half']
    trend=1 if row['trend']>0 else -1 if row['trend']<0 else 0
    if not trend or trend*row['other_move']<=0 or not liquid:return 0
    level=row['high_level'] if trend>0 else row['low_level']
    distance=trend*(level-row['close'])/row['atr']
    if method=='half_setup':
        active=(0<=distance<=p['near_atr'] and row['contraction']<=p['contraction']
                and trend*row['move']>=p['setup_move_atr'])
    elif method=='half_release':
        active=(distance<0 and trend*row['move']>=p['release_move_atr'])
    else:raise ValueError('unknown_half_method')
    return trend if active else 0


def schedule(raw,minute,f,rows,frozen):
    output={method:[] for method in METHODS};until={}
    for row in rows:
        stamp=row['bar_start'];end=row['generated_at']
        local=stamp.tz_convert('America/New_York')
        if local.dayofweek>=5 or not 570<=local.hour*60+local.minute<960:continue
        for method in METHODS:
            if method in until and end<until[method]:continue
            if method in ('half_setup','half_release'):
                side=direction(row,method)
            elif method=='no_signal':side=0
            else:
                start=stamp.floor('min')
                if stamp.second!=30 or start not in f.index:continue
                current=f.loc[start]
                side=(cross_rule(current,frozen['method'],frozen['params']) if method=='frozen_minute'
                      else candidate_signal(current,'breakout',{'rvol':1.3}))
            if side:
                output[method].append({'bar_start':stamp.isoformat(),'generated_at':end.isoformat(),
                                       'direction':int(side),'minute_start':stamp.floor('min').isoformat()})
                until[method]=end+pd.Timedelta(seconds=CONFIG['cooldown_seconds'])
    return output


def refine_events(events,minute,raw):
    """Keep canonical events/targets; refine first touch and close-onset timing.

    Comparing a half-minute signal against minute-close onset can manufacture
    an apparent early lead. Every method receives the same finer deadlines.
    """
    refined=[]
    for event in events:
        entry=float(minute.Close.iloc[event['anchor_index']])
        anchor=minute.index[event['anchor_index']]+pd.Timedelta(minutes=1)
        end=minute.index[event['target_index']]+pd.Timedelta(minutes=1)
        future=raw.loc[(raw.index>=anchor)&(raw.index<end)]
        direction=event['direction'];target=event['target_points']
        touched=(future.High>=entry+target) if direction>0 else (future.Low<=entry-target)
        hits=np.flatnonzero(touched.to_numpy())
        if not len(hits):raise ValueError('minute_target_missing_from_half_bars')
        hit=int(hits[0])
        onset=np.flatnonzero((direction*(future.Close.iloc[:hit+1]-entry)>=.25*target).to_numpy())
        # Original minute onset can occur at the target minute's second half,
        # after its first-half target touch. Keep it if needed, but that event
        # cannot be called actionable after the finer first target deadline.
        if not len(onset):
            onset=np.flatnonzero((direction*(future.Close-entry)>=.25*target).to_numpy())
        if not len(onset):raise ValueError('minute_onset_missing_from_half_bars')
        refined.append({**event,'onset_time_30s':(future.index[int(onset[0])]+pd.Timedelta(seconds=30)).isoformat(),
                        'target_start_30s':future.index[hit].isoformat(),
                        'anchor_completed_at':anchor.isoformat()})
    return refined


def score(events,signals,raw,minute,eligible,delay):
    eligible_times={minute.index[i] for i in eligible}
    scored=[];censored=[]
    for signal in signals:
        # Signal scheduling above is independent of these future-data checks.
        stamp=pd.Timestamp(signal['bar_start']);position=raw.index.get_loc(stamp)
        future=raw.iloc[position+1:position+21]
        valid=(pd.Timestamp(signal['minute_start']) in eligible_times and len(future)==20
               and future.index[-1]-stamp==pd.Timedelta(minutes=10)
               and bool(np.isfinite(future).all().all()) and bool((future.Volume>0).all())
               and bool(((future.Low>0)&(future.High>=future[['Open','Close','Low']].max(axis=1))&
                         (future.Low<=future[['Open','Close']].min(axis=1))).all()))
        (scored if valid else censored).append(signal)
    used=set();matches=[]
    for signal in scored:
        generated=pd.Timestamp(signal['generated_at']);delivered=generated+pd.Timedelta(seconds=delay)
        for event in events:
            # Late delivery cannot move a previously ineligible signal into an event.
            anchor=minute.index[event['anchor_index']]+pd.Timedelta(minutes=1)
            target=pd.Timestamp(event.get('target_start_30s',minute.index[event['target_index']]))
            if (event['event_id'] not in used and event['direction']==signal['direction']
                    and anchor<=generated<target and delivered<=target):
                used.add(event['event_id'])
                lead=(pd.Timestamp(event.get('onset_time_30s',event['onset_time']))-delivered).total_seconds()
                matches.append({'generated_at':generated.isoformat(),'delivered_at':delivered.isoformat(),
                                'event_id':event['event_id'],'lead_seconds':lead})
                break
    early=sum(m['lead_seconds']>0 for m in matches)
    timely=sum(m['lead_seconds']>=-60 for m in matches)
    n,e,h=len(scored),len(events),len(matches)
    return {'signals':n,'censored':len(censored),'events':e,'matched':h,'before_onset':early,
            'within_first_minute_or_before':timely,'false_alarms':n-h,'missed_events':e-h,
            'precision':h/n if n else None,'recall':h/e if e else None,
            'early_precision':early/n if n else None,'early_recall':early/e if e else None,
            'median_lead_seconds':float(np.median([m['lead_seconds'] for m in matches])) if matches else None,
            'precision_wilson_95':wilson(h,n),'early_precision_wilson_95':wilson(early,n),
            'matches':matches}


def missed_event_audit(events,rows,metrics):
    """Explain misses after scoring; labels never change signal generation."""
    matched={m['event_id'] for m in metrics['matches'] if m['lead_seconds']>0}
    result=[]
    for event in events:
        if event['event_id'] in matched:continue
        anchor=pd.Timestamp(event['anchor_completed_at'])
        onset=pd.Timestamp(event['onset_time_30s'])
        available=[r for r in rows if anchor<=r['generated_at']<onset]
        counts={}
        for row in available:
            if not row['valid']:
                reasons=['missing_or_invalid_past_context']
            else:
                side=event['direction']
                level=row['high_level'] if side>0 else row['low_level']
                distance=side*(level-row['close'])/row['atr']
                checks={'weak_relative_volume':row['rvol']<CONFIG['rvol_half'],
                        'prior_trend_opposes_event':side*row['trend']<=0,
                        'counterpart_does_not_confirm':side*row['other_move']<=0,
                        'weak_current_impulse':side*row['move']<CONFIG['release_move_atr'],
                        'prior_level_not_yet_released':distance>=0}
                reasons=[name for name,failed in checks.items() if failed]
                if not reasons:reasons=['candidate_cooldown_or_conservative_target_deadline']
            for reason in reasons:counts[reason]=counts.get(reason,0)+1
        result.append({'event_id':event['event_id'],'direction':event['direction'],
                       'anchor_completed_at':anchor.isoformat(),'onset_30s':onset.isoformat(),
                       'causal_halfminute_opportunities':len(available),
                       'no_completed_half_before_onset':not bool(available),
                       'gate_failures_counted_over_opportunities':counts})
    return result


def verify_protocol(root):
    root=Path(root)
    frozen=json.loads((root/'artifacts/halfminute-pilot/frozen.json').read_text())
    if frozen['config']!=CONFIG or frozen['methods']!=list(METHODS):
        raise ValueError('frozen_candidate_parameters_changed')
    source_hash=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    permitted={frozen['source_sha256']}
    amendment=root/'artifacts/halfminute-pilot/timing_amendment.json'
    if amendment.exists():permitted.add(json.loads(amendment.read_text())['corrected_source_sha256'])
    if source_hash not in permitted:raise ValueError('unfrozen_evaluator_source')
    return {'source_sha256':source_hash,'original_source_sha256':frozen['source_sha256'],
            'evaluation_amended':source_hash!=frozen['source_sha256']}


def run(inputs,root,output,cutoff):
    root=Path(root);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    protocol=verify_protocol(root)
    raw={s:normalize(blob) for s,blob in inputs.items()}
    for s in raw:
        raw[s]=raw[s].loc[raw[s].index+pd.Timedelta(seconds=30)<=pd.Timestamp(cutoff)]
        if inputs[s].get('chart_step')!=30:raise ValueError('provider_did_not_return_halfminute_bars')
    config=ResearchConfig()
    report={'status':'NOT_READY','protocol':protocol,
            'input_sha256':{s:hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest() for s,b in inputs.items()},
            'config':CONFIG,'cutoff':cutoff,'notifications_enabled':False,
            'training_or_tuning':False,'independent_sessions_established':False,
            'event_protocol':'Canonical minute events/targets unchanged. Onset refined to first 30s close reaching 25%; deadline refined to first target-touch 30s bar START.',
            'limitations':['Historical receipt latency and option bid/ask execution are absent.',
                           'Related symbols and previously inspected dates are correlated; not independent market validation.',
                           'RTH-only downloads may prevent opening warmup; missing windows are not filled.',
                           '30-second observations with 60-second polling may arrive too late; assumed delays are stressed explicitly.'],
            'symbols':{}}
    for sym,other in (('ES','NQ'),('NQ','ES')):
        minute,f,rows=prepared(raw[sym],raw[other])
        local=minute.index.tz_convert('America/New_York')
        idx=np.flatnonzero((local.hour*60+local.minute>=570)&(local.hour*60+local.minute<960)&(local.dayofweek<5)).tolist()
        context=_evaluation_context(minute,f,idx,'rth',config)
        context['events']=refine_events(context['events'],minute,raw[sym])
        frozen=json.loads(gzip.decompress((root/'artifacts/detector_v2'/f'crossmarket_v2_{sym.lower()}_report.json.gz').read_bytes()))['selected']
        signals=schedule(raw[sym],minute,f,rows,frozen)
        report['symbols'][sym]={'raw_rows':len(raw[sym]),'complete_minutes':len(minute),
            'first_bar':raw[sym].index[0].isoformat(),'last_bar':raw[sym].index[-1].isoformat(),
            'rth_dates':sorted(set(local[idx].strftime('%Y-%m-%d'))),
            'eligible_minutes':len(context['eligible']),'events':context['events'],'signals':signals,
            'metrics':{str(delay):{method:score(context['events'],signals[method],raw[sym],minute,context['eligible'],delay)
                      for method in METHODS} for delay in CONFIG['delays_seconds']}}
        report['symbols'][sym]['release_miss_audit_zero_delay']=missed_event_audit(
            context['events'],rows,report['symbols'][sym]['metrics']['0']['half_release'])
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--es',type=Path,required=True);p.add_argument('--nq',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--cutoff',required=True)
    a=p.parse_args()
    r=run({'ES':json.loads(a.es.read_text()),'NQ':json.loads(a.nq.read_text())},Path(__file__).parent,a.output,a.cutoff)
    print(json.dumps({s:{d:r['symbols'][s]['metrics'][d] for d in ('0','30','60')} for s in ('ES','NQ')}))
