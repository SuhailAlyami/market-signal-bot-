"""Research-only local/retest and exact-time ES/NQ confirmation hypotheses.

The retained four-week dataset was previously studied. Chronological test dates
are reused retrospective evaluation, NOT a newly untouched market holdout.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd

from hunter_research import (BASELINES, DEFAULT_PARAMS, ResearchConfig, benchmark,
                             candidate_signal, feature_frame)

METHODS = ('local_release', 'cross_local', 'cross_prelevel', 'retest_hold')


def paired_features(data, other):
    f = feature_frame(data)
    companion = feature_frame(other)
    f['local_high'] = data.High.shift(1).rolling(3).max()
    f['local_low'] = data.Low.shift(1).rolling(3).min()
    f['local_width'] = (f.local_high-f.local_low)/f.atr
    candle_range = data.High-data.Low
    f['close_position'] = (data.Close-data.Low)/candle_range.replace(0,np.nan)
    f['previous_close'] = data.Close.shift(1)
    f['previous_range_high'] = f.range_high.shift(1)
    f['previous_range_low'] = f.range_low.shift(1)
    # No forward fill/asof join. Missing counterpart minutes block confirmation.
    other_trend = (other.Close-other.Close.shift(3))/companion.atr
    f['other_trend'] = other_trend.reindex(data.index)
    f['other_valid'] = companion.valid.reindex(data.index).eq(True)
    return f


def signal(f, method, params):
    if method in BASELINES:
        return candidate_signal(f,method,params)
    if f is None or not f.get('valid',False):
        return 0
    p = {**DEFAULT_PARAMS, **params}
    liquid = f['rvol'] >= p['rvol']
    if method == 'cross_prelevel':
        direction = candidate_signal(f,'contraction_expansion',p)
        return direction if f['other_valid'] and direction*f['other_trend'] > 0 else 0
    if method in ('local_release','cross_local'):
        tight = f['local_width'] <= 3.
        up = (liquid and tight and f['close']>f['local_high'] and f['move']>=p['impulse']
              and f['trend_5']>0 and f['close_position']>=.65)
        down = (liquid and tight and f['close']<f['local_low'] and f['move']<=-p['impulse']
                and f['trend_5']<0 and f['close_position']<=.35)
        if method == 'cross_local':
            up = up and f['other_valid'] and f['other_trend']>0
            down = down and f['other_valid'] and f['other_trend']<0
    elif method == 'retest_hold':
        up = (liquid and f['previous_close']>f['previous_range_high']
              and f['low']<=f['previous_range_high']+.25*f['atr']
              and f['close']>f['previous_range_high']+.25*f['atr']
              and f['move']>0 and f['trend_5']>0)
        down = (liquid and f['previous_close']<f['previous_range_low']
                and f['high']>=f['previous_range_low']-.25*f['atr']
                and f['close']<f['previous_range_low']-.25*f['atr']
                and f['move']<0 and f['trend_5']<0)
    else:
        raise ValueError('unknown_crossmarket_method')
    return 1 if up and not down else -1 if down and not up else 0


def grid():
    result=[]
    for method,q,variant in itertools.product(METHODS,(.5,.75),(0,1)):
        params={**DEFAULT_PARAMS,'rvol_quantile':q,'impulse':(.3,.6)[variant],
                'proximity':(.2,.6)[variant], 'contraction':(.45,.65)[variant]}
        result.append({'id':f'{method}_q{q}_v{variant}','method':method,'params':params})
    return result


def run(es_path,nq_path,output,as_of):
    sources={}
    hashes={}
    for symbol,path in (('ES',es_path),('NQ',nq_path)):
        sources[symbol]=pd.read_csv(path,index_col=0,parse_dates=True)
        sources[symbol].index=pd.to_datetime(sources[symbol].index,utc=True)
        hashes[symbol]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    for symbol,other in (('ES','NQ'),('NQ','ES')):
        report,artifacts=benchmark(sources[symbol],symbol,'rth',pd.Timestamp(as_of),
                                  ResearchConfig(bootstrap_samples=500),
                                  feature_builder=lambda data:paired_features(data,sources[other]),
                                  signal_rule=signal,candidate_grid=grid(),availability_delays=(0,1,2,5,10))
        report.update(experiment='retrospective_crossmarket_v2',dataset_reused=True,
                      independent_untouched_holdout=False,source_sha256=hashes,notifications_enabled=False)
        report['limitations'].append('The same retained dataset was studied previously; this chronological test is reused retrospective evidence, not a newly untouched holdout.')
        for name,frame in artifacts.items():
            frame.to_csv(output/f'{symbol.lower()}_{name}.csv',index=False)
        (output/f'{symbol.lower()}_report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'symbol':symbol,'selected':report['selected']['id'],
                          'test':report['results']['test']},allow_nan=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--es',required=True)
    p.add_argument('--nq',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--as-of',required=True)
    a=p.parse_args()
    run(a.es,a.nq,a.output,a.as_of)
