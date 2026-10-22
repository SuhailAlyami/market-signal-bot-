"""Bounded new-resolution reads; reuse successful development day, never link tests."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import threading
import time

import pandas as pd
from ibapi.contract import Contract
from acquire_independent_history import HistoryClient,DATES


def acquire(output,protocol_commit,phase,development_report=None):
    if phase=='independent':
        report=json.loads(development_report.read_text())
        from validate_independent_reversal import absolute_gate
        qualified=absolute_gate(report.get('results',{}).get('fine',{}).get('0',{}).get('intrabar',{}))
        if not qualified or not report.get('development_promising') or report.get('rule_version') not in ('intrabar-sweep-v1','intrabar-sweep-carry-v1') or len(report.get('coverage',[]))!=10 or not all(c['complete'] for c in report['coverage']):
            raise ValueError('full_development_evidence_required_before_unused_requests')
        dates=json.loads(Path('docs/micro_range_locked_dates.json').read_text())
    else:dates=DATES
    output.mkdir(parents=True,exist_ok=True)
    if (output/'acquisition.json').exists():raise ValueError('acquisition_already_exists_do_not_repeat')
    metadata=dict(started_at=datetime.now(timezone.utc).isoformat(),protocol_commit=protocol_commit,
        phase=phase,requested_dates=dates,bar_size='5 secs',source='IBKR native ESU6/CME historical TRADES',
        orders_enabled=False,account_requests=False,paid_requests=False,requests=[])
    client=HistoryClient();frames=[]
    def run():
        try:client.connect('127.0.0.1',4001,clientId=20331031);client.run()
        except Exception as exc:metadata['connection_error_type']=type(exc).__name__;client.ready.set()
    threading.Thread(target=run,daemon=True).start()
    try:
        if not client.ready.wait(12) or not client.isConnected():raise RuntimeError('history_connection_unavailable')
        contract=Contract();contract.symbol='ES';contract.secType='FUT';contract.exchange='CME';contract.currency='USD'
        contract.lastTradeDateOrContractMonth='202609';contract.includeExpired=True;contract=client.resolve(101,contract)
        if contract is None:raise RuntimeError('actual_ES_contract_unresolved')
        contract.includeExpired=True
        metadata['contract']={k:getattr(contract,k) for k in ('conId','localSymbol','lastTradeDateOrContractMonth','exchange')}
        previous_request=0.
        for n,day in enumerate(dates):
            reused=Path('artifacts/micro_range_development/development_5sec_20260902.csv.gz')
            if phase=='development' and day=='2026-09-02' and reused.exists():
                frame=pd.read_csv(reused,index_col=0,parse_dates=True)
                metadata['requests'].append(dict(date=day,reused_source=str(reused),rows=len(frame),
                    sha256=hashlib.sha256(reused.read_bytes()).hexdigest()))
                (output/f'day_{day}.csv.gz').write_bytes(reused.read_bytes())
                frames.append(frame);print(json.dumps({'date':day,'status':'reused','rows':len(frame)}),flush=True);continue
            # Nine or twenty NEW requests only, below small-bar pacing limits.
            delay=2.2-(time.monotonic()-previous_request)
            if delay>0:time.sleep(delay)
            req=401+n;client.finished[req]=threading.Event()
            end=(datetime.fromisoformat(day)+timedelta(days=1)).strftime('%Y%m%d-00:00:00')
            record=dict(date=day,request_id=req,end_utc=end,duration='1 D',bar_size='5 secs',useRTH=1)
            metadata['requests'].append(record);previous_request=time.monotonic()
            client.reqHistoricalData(req,contract,end,'1 D','5 secs','TRADES',1,2,False,[])
            if not client.finished[req].wait(35):client.cancelHistoricalData(req);raise RuntimeError('historical_response_timeout')
            record['errors']=[e for e in client.errors if e['request_id']==req]
            rows=client.history.get(req,[]);record['rows']=len(rows)
            if record['errors'] or not rows:raise RuntimeError('historical_request_error_or_empty')
            frame=pd.DataFrame(rows,columns=['timestamp','Open','High','Low','Close','Volume'])
            frame.index=pd.to_datetime(frame.pop('timestamp'),unit='s',utc=True);frames.append(frame)
            frame.to_csv(output/f'day_{day}.csv.gz',compression='gzip')
            print(json.dumps({'date':day,'status':'new_data','rows':len(frame)}),flush=True)
        combined=pd.concat(frames).sort_index()
        if not combined.index.is_unique:raise ValueError('overlapping_source_timestamps_no_silent_dedupe')
        combined.to_csv(output/'native_es_5sec.csv.gz',compression='gzip')
        metadata.update(status='acquired',rows=len(combined),input_sha256=hashlib.sha256((output/'native_es_5sec.csv.gz').read_bytes()).hexdigest())
    except Exception as exc:metadata.update(status='blocked',blocker=str(exc),error_type=type(exc).__name__)
    finally:
        client.disconnect();metadata['errors']=client.errors;metadata['finished_at']=datetime.now(timezone.utc).isoformat()
        (output/'acquisition.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps({'status':metadata['status'],'blocker':metadata.get('blocker'),'rows':metadata.get('rows')}),flush=True)
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--protocol-commit',required=True);parser.add_argument('--phase',choices=['development','independent'],required=True)
    parser.add_argument('--development-report',type=Path)
    args=parser.parse_args();acquire(args.output,args.protocol_commit,args.phase,args.development_report)
