"""Bounded SPX/CBOE index and two option entitlement checks; market data only."""
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

from ibapi.contract import Contract
from gateway_hunter import DataClient, stamp


class Probe(DataClient):
    def __init__(self):
        super().__init__()
        self.by_request = {}; self.done = {}; self.chains = []
        self.chain_done = threading.Event(); self.quotes = {}; self.types = {}

    def contractDetails(self, reqId, details):
        self.by_request.setdefault(reqId, []).append(details.contract)

    def contractDetailsEnd(self, reqId):
        self.done.setdefault(reqId, threading.Event()).set()

    def marketDataType(self, reqId, kind):
        self.types[reqId] = kind

    def _record_quote(self, reqId, quote):
        records = self.quotes.setdefault(reqId, [])
        records.append(quote)
        if len(records) > 150:
            # Price callbacks can outnumber timestamp callbacks. Preserve the
            # latest actual provider times, including their original receipt;
            # retaining an old time must never make it current or REALTIME.
            pinned = {next(i for i in range(len(records)-1, -1, -1)
                           if records[i]['type'] == kind)
                      for kind in (45, 88)
                      if any(q['type'] == kind for q in records)}
            keep = set(range(len(records)-150, len(records))) | pinned
            for i in sorted(keep-pinned):
                if len(keep) <= 150:
                    break
                keep.remove(i)
            self.quotes[reqId] = [records[i] for i in sorted(keep)]

    def tickPrice(self, reqId, tickType, price, attrib):
        if price > 0:
            self._record_quote(reqId, {'type': tickType, 'price': price, 'received_at': stamp()})

    def tickString(self, reqId, tickType, value):
        if tickType in (45, 88):
            self._record_quote(reqId, {'type': tickType, 'value': value, 'received_at': stamp()})

    def securityDefinitionOptionParameter(self, reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes):
        if exchange == 'CBOE':
            self.chains.append({'exchange': exchange, 'trading_class': tradingClass,
                'multiplier': multiplier, 'expirations': sorted(expirations), 'strikes': sorted(strikes)})

    def securityDefinitionOptionParameterEnd(self, reqId):
        self.chain_done.set()

    def resolve(self, req, contract):
        self.done[req] = threading.Event()
        self.reqContractDetails(req, contract)
        self.done[req].wait(12)
        matches = self.by_request.get(req, [])
        return matches[0] if len(matches) == 1 else None


def main():
    client = Probe(); report = {'started_at': stamp(), 'orders_enabled': False, 'paid_snapshot': False}
    def run():
        try:
            client.connect('127.0.0.1', 4001, clientId=20331023); client.run()
        except Exception:
            client.lost = True
    threading.Thread(target=run, daemon=True).start()
    subscriptions = []
    try:
        if not client.ready.wait(12): raise RuntimeError('handshake_timeout')
        index = Contract(); index.symbol = 'SPX'; index.secType = 'IND'
        index.exchange = 'CBOE'; index.currency = 'USD'
        index = client.resolve(101, index)
        if index is None: raise RuntimeError('spx_contract_unresolved')
        report['index_contract_id'] = index.conId
        client.reqMarketDataType(1)
        client.reqMktData(201, index, '', False, False, []); subscriptions.append(201)
        client.reqSecDefOptParams(401, 'SPX', '', 'IND', index.conId)
        client.chain_done.wait(15); time.sleep(8)
        report['chains'] = client.chains
        prices = [q['price'] for q in client.quotes.get(201, []) if q.get('type') in (4,9,68,75)]
        report['option_selection_reference'] = 'observed last/close; not certified current'
        today = datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d')
        choices = [c for c in client.chains if c['trading_class'] == 'SPXW' and any(e >= today for e in c['expirations'])]
        report['options'] = []
        if choices and prices:
            chain = choices[0]; expiry = min(e for e in chain['expirations'] if e >= today)
            strike = min(chain['strikes'], key=lambda k: abs(k-prices[-1]))
            for n, right in enumerate(('C','P')):
                option = Contract(); option.symbol = 'SPX'; option.secType = 'OPT'
                option.exchange = 'CBOE'; option.currency = 'USD'; option.tradingClass = 'SPXW'
                option.lastTradeDateOrContractMonth = expiry; option.strike = strike
                option.right = right; option.multiplier = '100'
                resolved = client.resolve(102+n, option)
                if resolved:
                    req = 202+n; subscriptions.append(req)
                    report['options'].append({'request_id':req,'contract_id':resolved.conId,
                        'expiry':expiry,'strike':strike,'right':right})
                    client.reqMktData(req, resolved, '', False, False, [])
            time.sleep(12)
        else:
            report['option_probe_blocker'] = 'no_chain_or_observed_index_reference'
        report['realtime_request_types'] = dict(client.types)
        report['realtime_request_quotes'] = json.loads(json.dumps(client.quotes))
        report['realtime_request_errors'] = list(client.errors)
        # Explicit no-cost delayed fallback in separate request IDs.
        client.reqMarketDataType(3)
        client.reqMktData(211, index, '', False, False, []); subscriptions.append(211)
        time.sleep(10)
        report['market_data_types'] = client.types
        report['quotes'] = client.quotes
        report['errors'] = client.errors
        report['note'] = ('No order, account query or subscription purchase. Closed-market/frozen '
                          'quotes do not prove live freshness. Chain metadata alone is not quote entitlement.')
    except Exception as exc:
        report.update(status='probe_failed', error_type=type(exc).__name__, reason=str(exc))
    finally:
        for req in subscriptions:
            client.cancelMktData(req)
        client.disconnect(); report['finished_at'] = stamp()
        target = Path('.hunter-state/gateway/spx-probe.json'); target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report))


if __name__ == '__main__': main()

