"""Ten locked native historical reads; separate read-only client, no live changes."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import threading

import pandas as pd
from ibapi.contract import Contract
from gateway_spx_probe import Probe

DATES = ['2026-09-01','2026-09-02','2026-09-03','2026-09-04','2026-09-08',
         '2026-09-09','2026-09-10','2026-09-11','2026-09-14','2026-09-15']


class HistoryClient(Probe):
    def __init__(self):
        super().__init__(); self.history = {}; self.finished = {}

    def historicalData(self, reqId, bar):
        self.history.setdefault(reqId, []).append([int(bar.date),float(bar.open),float(bar.high),
            float(bar.low),float(bar.close),float(bar.volume)])

    def historicalDataEnd(self, reqId, start, end):
        self.finished.setdefault(reqId, threading.Event()).set()

    def error(self, reqId, errorCode, errorString, *extra):
        super().error(reqId,errorCode,errorString,*extra)
        if reqId >= 301:self.finished.setdefault(reqId,threading.Event()).set()


def acquire(output, protocol_commit):
    output.mkdir(parents=True, exist_ok=True)
    metadata=dict(started_at=datetime.now(timezone.utc).isoformat(), protocol_commit=protocol_commit,
        orders_enabled=False, account_requests=False, paid_requests=False, requested_dates=DATES,
        source='IBKR Gateway native historical TRADES; not a live quote test', requests=[])
    client=HistoryClient(); rows=[]
    def run():
        try:client.connect('127.0.0.1',4001,clientId=20331029);client.run()
        except Exception as exc:metadata['connection_error_type']=type(exc).__name__;client.ready.set()
    threading.Thread(target=run,daemon=True).start()
    try:
        if not client.ready.wait(12) or not client.isConnected():raise RuntimeError('history_handshake_failed')
        contract=Contract();contract.symbol='ES';contract.secType='FUT';contract.exchange='CME'
        contract.currency='USD';contract.lastTradeDateOrContractMonth='202609';contract.includeExpired=True
        resolved=client.resolve(101,contract)
        if resolved is None:raise RuntimeError('expired_ES_contract_unresolved')
        resolved.includeExpired=True
        metadata['contract']={k:getattr(resolved,k) for k in ('conId','localSymbol','lastTradeDateOrContractMonth','exchange','currency')}
        for n, day in enumerate(DATES):
            req=301+n;client.finished[req]=threading.Event()
            end=(datetime.fromisoformat(day)+timedelta(days=1)).strftime('%Y%m%d-00:00:00')
            record=dict(date=day, request_id=req, end_utc=end, duration='1 D', bar_size='1 min', useRTH=1)
            metadata['requests'].append(record)
            client.reqHistoricalData(req,resolved,end,'1 D','1 min','TRADES',1,2,False,[])
            if not client.finished[req].wait(35):
                client.cancelHistoricalData(req);raise RuntimeError('historical_response_timeout')
            errors=[e for e in client.errors if e['request_id']==req]
            record['errors']=errors;record['rows']=len(client.history.get(req,[]))
            rows.extend(client.history.get(req,[]))
            if errors or record['rows']==0:raise RuntimeError('historical_request_rejected_or_empty')
            print(json.dumps({'date':day,'rows':record['rows']}),flush=True)
        metadata['status']='acquired'
    except Exception as exc:
        metadata.update(status='blocked', blocker=str(exc), error_type=type(exc).__name__)
    finally:
        client.disconnect();metadata['errors']=client.errors
        if rows:
            frame=pd.DataFrame(rows,columns=['timestamp','Open','High','Low','Close','Volume'])
            if frame.timestamp.duplicated().any():
                # Preserve source observations; never silently dedupe/repair test data.
                metadata.update(status='blocked',blocker='overlapping_history_requests')
            frame.index=pd.to_datetime(frame.pop('timestamp'),unit='s',utc=True)
            frame.sort_index().to_csv(output/'native_es_1m.csv.gz',compression='gzip')
            metadata['input_sha256']=hashlib.sha256((output/'native_es_1m.csv.gz').read_bytes()).hexdigest()
        metadata['finished_at']=datetime.now(timezone.utc).isoformat()
        (output/'acquisition.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print(json.dumps({'status':metadata['status'],'blocker':metadata.get('blocker'),'errors':metadata['errors']}),flush=True)
    return metadata


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--protocol-commit',required=True)
    parser.add_argument('--output',type=Path,default=Path('artifacts/independent_reversal'))
    args=parser.parse_args();acquire(args.output,args.protocol_commit)
