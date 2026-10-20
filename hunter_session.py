"""Continuous NY IBKR research on an authorized host; alerts and orders OFF.

One ES/NQ acquisition per cycle is shared by canonical and frozen detectors.
The host retains OAuth and state; GitHub can launch the process remotely.
"""
import argparse
from contextlib import contextmanager
import asyncio
from datetime import datetime, timezone
import json
import os
import shutil
from pathlib import Path
import time

import pandas as pd

from ibkr_feed_preflight import inspect as inspect_auth
from ny_intraday_shadow import session_at, run as ny_run
from globex_render_worker import create_runtime, run_once


def default_state_dir():
    # Survives Actions checkout cleanup and is shared by same-user launches.
    return Path.home()/'.local/state/suhail-hunter/ibkr-session'


def export_telemetry(source, destination):
    source=Path(source).resolve();destination=Path(destination)
    allowed={'session-heartbeat.json','state-ibkr.json','shadow-ibkr.jsonl','ny-heartbeat.json'}
    exported=[]
    if not source.exists():return exported
    for path in source.rglob('*'):
        relative=path.relative_to(source)
        if (path.is_symlink() or not path.is_file() or
            any(parent.is_symlink() for parent in path.parents if source in parent.parents) or
            len(relative.parts)>2):
            continue
        accepted=path.name in allowed or (relative.parts[0]=='ny' and
                 ((path.name.startswith('ny-ibkr-') and path.suffix=='.json') or
                  (path.name.startswith('ny-candidates-') and path.suffix=='.jsonl')))
        if not accepted:continue
        target=destination/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        exported.append(str(relative))
    return exported


async def authorize():
    from ibkr_mcp_client import run_collection
    async def initialized(call):
        # Successful OAuth + initialized MCP session; no account or order calls.
        return {'status':'AUTHORIZED_CONNECTION', 'feed_realtime_verified':False,
                'readiness':'NOT_READY', 'orders_enabled':False}
    return await run_collection(authorize=True, collector=initialized)


def cycle(directory, *, now=None, clock=None, fetch=None, auth=None, canonical=None, ny=None):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    clock=clock or (lambda:datetime.now(timezone.utc))
    now=pd.Timestamp(now if now is not None else clock())
    session,status=session_at(now)
    report={'checked_at':now.isoformat(), 'status':status, 'source':'IBKR MCP',
            'readiness':'NOT_READY','notifications_enabled':False,'orders_enabled':False,
            'code_revision':os.getenv('GITHUB_SHA')}
    if session is not None:
        report.update(market_open=session.market_open.isoformat(),market_close=session.market_close.isoformat())
    if status=='NY_OPEN':
        health=auth() if auth else asyncio.run(inspect_auth())
        report['authorization']=health['status']
        if not health.get('runtime_auth_present'):
            report['status']='AUTHORIZATION_REQUIRED'
        else:
            if fetch is None:
                from ibkr_market_data import fetch_bars
                fetch=fetch_bars
            cache={}
            errors={}
            def shared(symbol):
                key=symbol.removesuffix('=F')
                if key in errors:
                    raise errors[key]
                if key not in cache:
                    try:cache[key]=fetch(key)
                    except Exception as exc:
                        errors[key]=exc
                        raise
                return cache[key].copy()
            canonical=canonical or (lambda f:run_once(create_runtime(directory),fetcher=f))
            ny=ny or (lambda f:ny_run(directory/'ny',fetch=f,clock=clock))
            # Each consumer retains its own fail-closed checks and journaling.
            result=canonical(shared)
            report['canonical_heartbeat']=result['heartbeat']
            frozen=ny(shared)
            report['frozen_status']=frozen['status']
            report['new_frozen_candidates']=len(frozen.get('new_candidates',[]))
            report['feed_metadata']={sym:dict(frame.attrs) for sym,frame in cache.items()}
            report['status']='OBSERVED' if (result['heartbeat']['status']=='ok' and frozen['status']=='NY_OPEN') else 'DATA_UNAVAILABLE'
            auth_reasons={'authorize_runtime_separately','renew_runtime_authorization','authorization_required'}
            failures=[v.get('data_status') for v in result['heartbeat'].get('symbols',{}).values()]
            failures.append(frozen.get('data_status'))
            if any(reason in auth_reasons for reason in failures):
                report['status']='AUTHORIZATION_REQUIRED'
    temporary=directory/'session-heartbeat.tmp'
    temporary.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    temporary.replace(directory/'session-heartbeat.json')
    return report


def run_loop(directory, *, interval=60, max_hours=16, once=False, clock=None,
             monotonic=None, sleep=None, tick=None):
    if interval<60 or not 0<max_hours<=24:
        raise ValueError('interval_at_least_60_seconds_and_hours_in_0_24_required')
    clock=clock or (lambda:datetime.now(timezone.utc))
    monotonic=monotonic or time.monotonic
    sleep=sleep or time.sleep
    tick=tick or (lambda:cycle(directory,clock=clock))
    deadline=monotonic()+max_hours*3600
    count=0;report={}
    while monotonic()<deadline:
        started=monotonic()
        report=tick();count+=1
        print(json.dumps({'status':report['status'],'checked_at':report.get('checked_at'),
                          'cycles':count,'notifications_enabled':False}),flush=True)
        if once or report['status'] in {'NY_CLOSED','NONTRADING_DAY','AUTHORIZATION_REQUIRED'}:
            break
        # Start-to-start cadence; network time is not added to the interval.
        remaining=min(interval-(monotonic()-started),deadline-monotonic())
        # Short sleeps allow interruption without a long uninterruptible wait.
        while remaining>0:
            nap=min(remaining,1.)
            sleep(nap)
            remaining=min(interval-(monotonic()-started),deadline-monotonic())
    return report


@contextmanager
def collector_lock(directory):
    """OS releases the lock even after a crash; supports Windows and POSIX."""
    path=Path(directory)
    path.mkdir(parents=True,exist_ok=True)
    stream=(path/'.collector.lock').open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            if stream.seek(0,2)==0:
                stream.write(b'0');stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise RuntimeError('Another collector already owns this state directory') from None
    try:
        yield
    finally:
        stream.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir',default=str(default_state_dir()))
    parser.add_argument('--export-only',metavar='DIRECTORY',help='export allowlisted telemetry, no authentication or scans')
    parser.add_argument('--interval',type=int,default=60)
    parser.add_argument('--max-hours',type=float,default=16)
    parser.add_argument('--once',action='store_true')
    parser.add_argument('--authorize',action='store_true',help='one-time same-host IBKR OAuth; never in GitHub logs')
    args=parser.parse_args()
    if args.export_only:
        print(json.dumps({'exported':export_telemetry(args.state_dir,args.export_only)}))
        return 0
    try:
        with collector_lock(args.state_dir):
            if args.authorize:
                if os.getenv('GITHUB_ACTIONS'):
                    raise SystemExit('Interactive authorization must run locally, outside GitHub logs')
                result=asyncio.run(authorize())
                print(json.dumps(result))
                if result.get('status')!='AUTHORIZED_CONNECTION':
                    return 1
            result=run_loop(args.state_dir,interval=args.interval,max_hours=args.max_hours,once=args.once)
    except KeyboardInterrupt:
        return 0
    return 1 if result.get('status') in {'AUTHORIZATION_REQUIRED','DATA_UNAVAILABLE'} else 0


if __name__=='__main__':
    raise SystemExit(main())
