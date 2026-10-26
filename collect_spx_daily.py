"""One read-only local Gateway export, with raw evidence and strict daily validation."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import pandas as pd
from collect_spx_sessions import gateway, request_end, write_json
from spx_daily import schedule, connect, ingest


def evaluate_capture(output):
    """Run only the frozen 2025 experiment from a validated acquisition."""
    from evaluate_spx_daily import evaluate
    output=Path(output)
    if (output/'evaluation.json').exists():
        raise FileExistsError('evaluation already recorded')
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf-8'))
    if not manifest.get('data_complete'):
        raise ValueError('capture not validated')
    import hashlib
    encoded=(output/'input.json').read_bytes()
    if hashlib.sha256(encoded).hexdigest()!=manifest['input_sha256']:
        raise ValueError('input hash mismatch')
    if hashlib.sha256((output/'raw.json').read_bytes()).hexdigest()!=manifest['raw_sha256']:
        raise ValueError('raw hash mismatch')
    document=json.loads(encoded)
    rows=document['bars']
    if rows[0]['date']!='2024-10-28' or rows[-1]['date']!='2025-12-31':
        raise ValueError('capture does not match frozen experiment bounds')
    with closing(connect(':memory:')) as db:
        ingest(db,document)
    report=evaluate(rows,'2025-04-01','2025-07-01')
    write_json(output/'evaluation.json',report)
    return report


def plan(start, end, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError('timezone required')
    cal=schedule(start,end)
    if len(cal)<81 or len(cal)>500:
        raise ValueError('require 81..500 consecutive completed sessions')
    if str(cal.index[0].date())!=start or str(cal.index[-1].date())!=end:
        raise ValueError('bounds must be actual NYSE sessions')
    if cal.iloc[-1].market_close>now:
        raise ValueError('end session incomplete')
    # The reader's one request covers two calendar years only.
    if pd.Timestamp(start)<pd.Timestamp(end)-pd.DateOffset(years=2)+pd.Timedelta(days=1):
        raise ValueError('requested bounds exceed two-year request')
    return cal


def normalize(raw, start, end):
    """No sorting, deduplication, correction or gap filling of provider prices."""
    rows=[]; outside=0; previous=None
    for row in raw:
        stamp=str(row['time'])
        if len(stamp)!=8 or not stamp.isdigit():
            raise ValueError('daily date must be yyyyMMdd')
        day=datetime.strptime(stamp,'%Y%m%d').date().isoformat()
        if previous is not None and day<=previous:
            raise ValueError('daily dates must be unique and ascending')
        previous=day
        if day<start or day>end:
            outside+=1
            continue
        rows.append(dict(date=day,**{k:float(row[k]) for k in ('open','high','low','close')}))
    if not rows or rows[0]['date']!=start or rows[-1]['date']!=end:
        raise ValueError('requested boundary session missing')
    return dict(source='IBKR',symbol='SPX',security_type='IND',bars=rows),outside


def collect(start, end, output, port=4001, client_id=20331026, now=None):
    cal=plan(start,end,now)
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    report=dict(status='WAIT_VALID_DATA',data_complete=False,orders_enabled=False,
                notifications_enabled=False,live_feed_verified=False,
                source='IBKR_TWS_API_HISTORY',start=start,end=end,
                expected_sessions=len(cal),request_count=0)
    reader=None
    try:
        reader=gateway(port,client_id)
        contract=reader.resolve()
        identity=dict(symbol=contract.symbol,security_type=contract.secType,
                      exchange=contract.exchange,currency=contract.currency,
                      contract_id=contract.conId)
        if (identity['symbol'],identity['security_type'],identity['exchange'],identity['currency'])!=('SPX','IND','CBOE','USD') or identity['contract_id']<=0:
            raise ValueError('wrong native contract')
        close=cal.iloc[-1].market_close
        report['request_count']=1
        raw,bounds=reader.daily_history(contract,close,2101)
        received=datetime.now(timezone.utc).isoformat()
        report['raw_sha256']=write_json(output/'raw.json',dict(contract=identity,
            received_at=received,request=dict(endDateTime=request_end(close),durationStr='2 Y',
            barSizeSetting='1 day',whatToShow='TRADES',useRTH=1,formatDate=1,keepUpToDate=False),
            bounds=bounds,bars=raw))
        document,outside=normalize(raw,start,end)
        report['outside_requested_sessions']=outside
        # The exact raw export is retained even if native OHLC are inconsistent.
        with closing(connect(':memory:')) as db:
            rows=ingest(db,document,now=now)
        if len(rows)!=len(cal):
            raise ValueError('incomplete daily history')
        document.update(contract=identity,received_at=received,raw_sha256=report['raw_sha256'])
        report['input_sha256']=write_json(output/'input.json',document)
        report.update(status='VALIDATED_HISTORY_NOT_PREDICTIVE_PROOF',data_complete=True,sessions=len(rows))
    except Exception as exc:
        # Do not emit raw provider messages or connection details into status output.
        report['failure_type']=type(exc).__name__
    finally:
        if reader is not None:
            try:
                reader.disconnect()
            except Exception:
                report['disconnect_failed']=True
        write_json(output/'manifest.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--start',required=True);p.add_argument('--end',required=True)
    p.add_argument('--output',required=True);p.add_argument('--port',type=int,default=4001)
    p.add_argument('--evaluate-protocol',action='store_true')
    args=p.parse_args()
    if args.evaluate_protocol and (args.start,args.end)!=('2024-10-28','2025-12-31'):
        p.error('--evaluate-protocol requires frozen 2024-10-28..2025-12-31 bounds')
    result=collect(args.start,args.end,args.output,args.port)
    if args.evaluate_protocol and result['data_complete']:
        result['evaluation_status']=evaluate_capture(args.output)['status']
    print(json.dumps(result))
    raise SystemExit(0 if result['data_complete'] else 2)
