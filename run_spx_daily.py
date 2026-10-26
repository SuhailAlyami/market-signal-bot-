"""Persistent read-only post-close daily research cycle; no notifications or orders."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import time
import pandas as pd
from collect_spx_daily import collect
from spx_daily import connect, ingest, issue, schedule


def source_window(now):
    now=pd.Timestamp(now)
    if now.tzinfo is None:
        raise ValueError('timezone required')
    cal=schedule(now.date()-pd.Timedelta(days=800),now.date())
    # Five minutes after the actual NYSE close, including early-close sessions.
    complete=cal.loc[cal.market_close+pd.Timedelta(minutes=5)<=now].tail(252)
    if len(complete)<252:
        raise ValueError('insufficient calendar')
    return str(complete.index[0].date()),str(complete.index[-1].date())


def load_capture(directory, now):
    directory=Path(directory)
    manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('data_complete'):
        raise ValueError('capture incomplete')
    raw_bytes=(directory/'raw.json').read_bytes()
    input_bytes=(directory/'input.json').read_bytes()
    if hashlib.sha256(raw_bytes).hexdigest()!=manifest['raw_sha256'] or hashlib.sha256(input_bytes).hexdigest()!=manifest['input_sha256']:
        raise ValueError('capture hash mismatch')
    document=json.loads(input_bytes)
    if document.get('raw_sha256')!=manifest['raw_sha256']:
        raise ValueError('input provenance mismatch')
    if (document['bars'][0]['date'],document['bars'][-1]['date'])!=(manifest['start'],manifest['end']):
        raise ValueError('capture bounds mismatch')
    # Recheck values/calendar even after an allegedly successful acquisition.
    with closing(connect(':memory:')) as db:
        ingest(db,document,now)
    return document


def cycle(root, now=None, collector=collect):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    start,end=source_window(now)
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    state_path=root/'runs.sqlite'
    with closing(sqlite3.connect(state_path,timeout=30)) as state:
        state.execute('CREATE TABLE IF NOT EXISTS runs (session TEXT PRIMARY KEY, started_at TEXT NOT NULL, status TEXT NOT NULL, payload TEXT)')
        # Reserve before acquisition: concurrent processes/restarts never duplicate
        # a historical request. Unfinished reservations require explicit recovery.
        with state:
            state.execute('BEGIN IMMEDIATE')
            prior=state.execute('SELECT status,payload FROM runs WHERE session=?',(end,)).fetchone()
            if prior:
                return dict(status='ALREADY_ATTEMPTED',source_session=end,
                            previous_status=prior[0],previous_result=json.loads(prior[1]) if prior[1] else None)
            state.execute('INSERT INTO runs VALUES (?,?,?,NULL)',(end,now.isoformat(),'RUNNING'))
        result=dict(status='WAIT_VALID_DATA',source_session=end,as_of=now.isoformat(),
                    research_only=True,orders_enabled=False,notifications_enabled=False)
        capture=root/'captures'/end
        try:
            report=collector(start,end,capture,now=now)
            result['capture_status']=report['status']
            if report.get('data_complete'):
                document=load_capture(capture,now)
                if document['bars'][-1]['date']!=end:
                    raise ValueError('latest source session missing')
                with closing(connect(root/'spx-daily.sqlite')) as db:
                    # Ingest scores previous immutable forecasts before learning.
                    ingest(db,document,now)
                    try:
                        prediction=issue(db,now)
                    except ValueError as exc:
                        result['status']='SCORED_NO_NEW_PREDICTION'
                        result['reason']=str(exc)
                    else:
                        result.update(status='RESEARCH_FORECAST_ISSUED',prediction=prediction)
        except Exception as exc:
            # Preserve raw artifacts and avoid provider/account error text.
            result['failure_type']=type(exc).__name__
        with state:
            state.execute('UPDATE runs SET status=?,payload=? WHERE session=?',
                          (result['status'],json.dumps(result,allow_nan=False),end))
        return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--state-dir',default='.hunter-state/daily')
    parser.add_argument('--watch-seconds',type=int,default=0)
    args=parser.parse_args()
    while True:
        print(json.dumps(cycle(args.state_dir),allow_nan=False),flush=True)
        if not args.watch_seconds:
            break
        time.sleep(max(60,args.watch_seconds))
