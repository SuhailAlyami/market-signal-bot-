"""After-close, fixed-candidate research on newly completed ES/NQ sessions.

No alerts, model retuning, Render, brokerage OAuth or option-return claims.
Historical minute replay after close is not a live point-in-time paper log.
"""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import numpy as np

from hunter_crossmarket_research import signal as cross_rule
from hunter_linear_research import fit_for, matrix_features, rule as model_rule
from hunter_research import (ResearchConfig,_evaluation_context,_evaluate,
                             chronological_splits,validate_bars)

FROZEN_FIRST_DAY='2026-10-20'


def closed_session(now):
    import pandas_market_calendars as mcal
    now=pd.Timestamp(now)
    if now.tz is None:raise ValueError('aware_clock_required')
    day=now.tz_convert('America/New_York').date()
    schedule=mcal.get_calendar('NYSE').schedule(start_date=day,end_date=day)
    if schedule.empty:return None,'NONTRADING_DAY'
    close=schedule.iloc[0].market_close
    if now<close+pd.Timedelta(minutes=20):return None,'WAITING_FOR_CLOSED_SESSION'
    if str(day)<FROZEN_FIRST_DAY:return None,'BEFORE_FROZEN_FORWARD_WINDOW'
    return schedule.iloc[0],'CLOSED_SESSION'


def read_report(root,kind,symbol):
    path=root/'artifacts/detector_v2'/f'{kind}_{symbol.lower()}_report.json.gz'
    return json.loads(gzip.decompress(path.read_bytes()))


def check_day_coverage(data,session):
    expected=pd.date_range(session.market_open,session.market_close-pd.Timedelta(minutes=1),freq='min')
    missing=expected.difference(data.index)
    if len(missing):return False,f'missing_{len(missing)}_session_minutes'
    current=data.loc[expected]
    valid=np.isfinite(current).all(axis=1)&(current.Volume>0)&(current.Low>0)&(current.High>=current[['Open','Close']].max(axis=1))&(current.Low<=current[['Open','Close']].min(axis=1))
    if not bool(valid.all()):return False,'invalid_or_inactive_session_bars'
    return True,None


def evaluate_new_day(original,fresh,session,root):
    from hunter_boosted_research import fit_boosted
    config=ResearchConfig(bootstrap_samples=500)
    source_hash={sym:hashlib.sha256((root/f'artifacts/issue16/data/{sym.lower()}_1m.csv.gz').read_bytes()).hexdigest() for sym in original}
    combined={}
    for sym in original:
        # Retained development data are never overwritten by revised downloads.
        combined[sym]=pd.concat([original[sym],fresh[sym].loc[~fresh[sym].index.isin(original[sym].index)] ]).sort_index()
        combined[sym]=combined[sym].loc[combined[sym].index+pd.Timedelta(minutes=1)<=session.market_close]
    reports={};logs={}
    for sym,other in (('ES','NQ'),('NQ','ES')):
        f=matrix_features(combined[sym],combined[other])
        indices=[i for i,stamp in enumerate(combined[sym].index) if session.market_open<=stamp<session.market_close]
        context=_evaluation_context(combined[sym],f,indices,'rth',config)
        rule_report=read_report(root,'crossmarket_v2',sym)
        linear_report=read_report(root,'linear_v2',sym)
        boost_report=read_report(root,'boosted_v2',sym)
        for report in (rule_report,linear_report,boost_report):
            if report['source_sha256']!=source_hash:raise ValueError('frozen_training_source_changed')
        # Reproduce the frozen boosted estimator from the SAME original train
        # prefix and hyperparameters. No new-day input enters its fitting.
        old_f=matrix_features(original[sym],original[other])
        split,_=chronological_splits(original[sym],'rth',pd.Timestamp('2026-10-19T09:00:51Z'),config.horizon)
        strength=boost_report['selected']['params']['model']['regularization']
        boosted=fit_for(original[sym],old_f,split['train'],config,strength,fit_boosted)
        if boosted['sklearn_version']!=boost_report['selected']['params']['model']['sklearn_version']:
            raise ValueError('frozen_model_library_version_changed')
        candidates={
            'crossmarket':(rule_report['selected']['method'],rule_report['selected']['params'],cross_rule),
            'linear':('linear',linear_report['selected']['params'],model_rule),
            'boosted':('boosted',{'model':boosted,'threshold':boost_report['selected']['params']['threshold']},model_rule),
            'baseline_breakout':('breakout',{'rvol':1.3},model_rule),
            'baseline_trend':('trend_persistence',{},model_rule)}
        reports[sym]={}
        for name,(method,params,rule) in candidates.items():
            m,e,s=_evaluate(combined[sym],f,indices,method,params,'rth',config,True,
                            _context=context,signal_rule=rule)
            reports[sym][name]=m
            logs[sym+'_'+name]={'events':e,'signals':s}
    return reports,logs


def run(output,root=None,now=None,fetch=None):
    root=Path(root or Path(__file__).parent)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    session,status=closed_session(now)
    report={'status':status,'observed_at':now.isoformat(),'notifications_enabled':False,
            'code_revision':os.getenv('GITHUB_SHA'),
            'readiness':'NOT_READY','forward_window_starts':FROZEN_FIRST_DAY,
            'protocol':'Fixed candidates; newly completed session; after-close historical replay, not real-time paper execution.'}
    if session is not None:
        report['frozen_candidate_report_sha256']={
            f'{kind}_{sym}':hashlib.sha256((root/'artifacts/detector_v2'/f'{kind}_{sym}_report.json.gz').read_bytes()).hexdigest()
            for kind in ('crossmarket_v2','linear_v2','boosted_v2') for sym in ('es','nq')}
        originals={};fresh={};quality={}
        for sym in ('ES','NQ'):
            path=root/f'artifacts/issue16/data/{sym.lower()}_1m.csv.gz'
            originals[sym]=pd.read_csv(path,index_col=0,parse_dates=True)
            originals[sym].index=pd.to_datetime(originals[sym].index,utc=True)
        if fetch is None:
            import yfinance as yf
            fetch=lambda sym:yf.Ticker(sym+'=F').history(period='5d',interval='1m',auto_adjust=False,raise_errors=True)
        for sym in ('ES','NQ'):
            try:
                data=fetch(sym)[['Open','High','Low','Close','Volume']]
                fresh[sym]=validate_bars(data)
                okay,reason=check_day_coverage(fresh[sym],session)
                quality[sym]={'okay':okay,'reason':reason}
            except Exception as exc:
                quality[sym]={'okay':False,'error_type':type(exc).__name__}
        report['source_quality']=quality
        report['session_date']=str(session.market_open.tz_convert('America/New_York').date())
        if all(x['okay'] for x in quality.values()):
            metrics,logs=evaluate_new_day(originals,fresh,session,root)
            report.update(status='FORWARD_DAY_REPLAY_COMPLETE',metrics=metrics,
                          caveats=['New future sessions provide new classification evidence, not live option execution evidence.',
                                   'Historical bars may be revised; publication latency and bid/ask are absent.',
                                   'One session cannot establish reliability; no automatic model promotion.'])
            for sym,data in fresh.items():
                raw_path=output/(sym.lower()+'_download.csv.gz')
                data.to_csv(raw_path,compression={'method':'gzip','mtime':0})
                report.setdefault('source_sha256',{})[sym]=hashlib.sha256(raw_path.read_bytes()).hexdigest()
            (output/'events_and_signals.json').write_text(json.dumps(logs,indent=2,allow_nan=False)+'\n')
        else:
            report['status']='DATA_UNAVAILABLE_NO_OUTCOMES_INFERRED'
    target=output/'report.json'
    target.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    summary=os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary,'a') as stream:
            stream.write('## Frozen detector forward-day research\n\nNo notifications or automatic promotion.\n\n```json\n'+json.dumps(report,indent=2,allow_nan=False)+'\n```\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    r=run(a.output)
    print(json.dumps({'status':r['status'],'session':r.get('session_date'),'readiness':r['readiness']}))
