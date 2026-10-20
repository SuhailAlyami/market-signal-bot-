"""Verify one connected-tool IBKR capture and run Hunter at actual processing time.

Only market data are accepted. This is one receipt, not autonomous OAuth for
GitHub. Stale captures never earn backdated detections. No notifications/orders.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd

from ibkr_mcp import inspect_snapshot
from ibkr_market_data import normalize
from globex_render_worker import create_runtime, run_once
from ny_intraday_shadow import session_at


def verify(capture, output, now=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tz is None:raise ValueError('aware_processing_clock_required')
    report={'processed_at':now.isoformat(),'source':'IBKR connected market-data tools',
            'readiness':'NOT_READY','notifications_enabled':False,'orders_enabled':False,
            'capture_is_autonomous_runtime_authorization':False,'symbols':{}}
    frames={}
    for symbol in ('ES','NQ'):
        record=capture['symbols'][symbol]
        receipt=pd.Timestamp(record['received_at'])
        if receipt.tz is None or receipt>now:raise ValueError('invalid_receipt_time')
        quote=inspect_snapshot(record['snapshot'],now.to_pydatetime(),max_age_seconds=60)
        frame=normalize(record['history'])
        frame=frame.loc[frame.index+pd.Timedelta(minutes=1)<=now]
        bar_age=None if frame.empty else (now-frame.index[-1]-pd.Timedelta(minutes=1)).total_seconds()
        valid=(quote['last_live_verified'] and record['history'].get('delayed') in (None,0,False)
               and bar_age is not None and 0<=bar_age<=120)
        report['symbols'][symbol]={'feed_status':quote['feed_status'],'last_trade_at':quote['last_trade_at'],
                                  'last_trade_age_seconds':quote['last_trade_age_seconds'],
                                  'received_at':receipt.isoformat(),'latest_bar_age_seconds':bar_age,
                                  'rows':len(frame),'live_input_verified':bool(valid),
                                  'contract_month':record['contract']['contract_month'],
                                  'history_source':record['history'].get('source'),
                                  'bar_publication_latency_verified':False}
        if valid:
            frame.attrs.update(source='IBKR MCP',live_feed_verified=True,
                               observed_at=receipt.isoformat(),feed_status=quote['feed_status'])
            frames[symbol]=frame
    report['ny_session_status']=session_at(now)[1]
    if len(frames)==2:
        # Processing clock is NOW, never the saved quote/candle timestamp.
        result=run_once(create_runtime(output/'runtime'),now=now.to_pydatetime(),
                        fetcher=lambda s:frames[s.removesuffix('=F')])
        report['heartbeat']=result['heartbeat']
        report['events']=result['events']
        report['status']='VERIFIED_CAPTURE_ANALYZED' if result['heartbeat']['status']=='ok' else 'DETECTOR_REJECTED_INPUT'
    else:
        report['status']='STALE_OR_UNVERIFIED_INPUT_REJECTED'
        report['events']=[]
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    capture=json.loads(a.capture.read_text())
    result=verify(capture,a.output)
    print(json.dumps({'status':result['status'],'processed_at':result['processed_at'],
                      'symbols':result['symbols'],'ny_session_status':result['ny_session_status'],
                      'events':result['events']},allow_nan=False))
