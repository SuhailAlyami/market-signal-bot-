"""Two bounded new-data requests, NOT connection/permission retry loops."""
import gzip
import json
from pathlib import Path
import threading
from datetime import datetime,timezone
from ibapi.contract import Contract
from acquire_independent_history import HistoryClient


class TapeHistory(HistoryClient):
    def __init__(self):super().__init__();self.tape={}
    def historicalTicksBidAsk(self,reqId,ticks,done):
        self.tape.setdefault(reqId,[]).extend(dict(time=int(t.time),bid=float(t.priceBid),ask=float(t.priceAsk),
            bid_size=float(t.sizeBid),ask_size=float(t.sizeAsk)) for t in ticks)
        if done:self.finished[reqId].set()
    def historicalTicksLast(self,reqId,ticks,done):
        self.tape.setdefault(reqId,[]).extend(dict(time=int(t.time),price=float(t.price),size=float(t.size),exchange=t.exchange) for t in ticks)
        if done:self.finished[reqId].set()


def main():
    output=Path('artifacts/tape_development_probe');output.mkdir(parents=True,exist_ok=True)
    client=TapeHistory();report=dict(started_at=datetime.now(timezone.utc).isoformat(),orders_enabled=False,
        usage='consumed_development_capability_and_sampling_span_only',requests=[])
    def run():
        try:client.connect('127.0.0.1',4001,clientId=20331033);client.run()
        except Exception as exc:report['connection_error_type']=type(exc).__name__;client.ready.set()
    threading.Thread(target=run,daemon=True).start()
    try:
        if not client.ready.wait(12) or not client.isConnected():raise RuntimeError('data_connection_unavailable')
        contract=Contract();contract.symbol='ES';contract.secType='FUT';contract.exchange='CME';contract.currency='USD'
        contract.lastTradeDateOrContractMonth='202609';contract.includeExpired=True;contract=client.resolve(101,contract)
        if contract is None:raise RuntimeError('expired_contract_unresolved')
        contract.includeExpired=True;report['contract_id']=contract.conId
        for req,kind in ((501,'BID_ASK'),(502,'TRADES')):
            client.finished[req]=threading.Event()
            client.reqHistoricalTicks(req,contract,'20260902-14:00:00','',1000,kind,1,False,[])
            done=client.finished[req].wait(20);ticks=client.tape.get(req,[])
            report['requests'].append(dict(kind=kind,completed=done,rows=len(ticks),
                span_seconds=ticks[-1]['time']-ticks[0]['time'] if ticks else None,
                errors=[e for e in client.errors if e['request_id']==req]))
        report['status']='available' if all(r['rows'] for r in report['requests']) else 'incomplete_or_unavailable'
    except Exception as exc:report.update(status='blocked',blocker=str(exc))
    finally:
        client.disconnect();report['finished_at']=datetime.now(timezone.utc).isoformat()
        with gzip.open(output/'sample.json.gz','wt',encoding='utf-8') as stream:json.dump(client.tape,stream)
        (output/'availability.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
