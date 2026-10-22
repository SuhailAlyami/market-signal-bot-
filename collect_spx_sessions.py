"""Read-only SPX historical acquisition through the local official TWS API.

One explicit UTC end per NYSE session. No orders, accounts, live-price claims,
gap filling, strategy changes or Telegram delivery.
"""
import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import threading
import time

import pandas as pd
import pandas_market_calendars as mcal


def sessions(end, count, now=None):
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    if not 1 <= count <= 60:
        raise ValueError('sessions_must_be_1_to_60')
    end = date.fromisoformat(end)
    schedule = mcal.get_calendar('NYSE').schedule(
        start_date=end - timedelta(days=count * 3 + 30), end_date=end)
    schedule = schedule.loc[schedule.market_close <= now].tail(count)
    if len(schedule) != count:
        raise ValueError('not_enough_completed_sessions')
    return [(str(day.date()), row.market_open, row.market_close)
            for day, row in schedule.iterrows()]


def request_end(close):
    return pd.Timestamp(close).tz_convert('UTC').strftime('%Y%m%d-%H:%M:%S')


def validate_session(rows, opened, closed):
    """Keep raw separately; validate/deduplicate the session-specific view only."""
    expected = pd.date_range(opened, closed, freq='min', inclusive='left')
    selected = {}
    duplicates = outside = 0
    previous = None
    for row in rows:
        stamp = pd.Timestamp(int(row['time']), unit='s', tz='UTC')
        if previous is not None and stamp < previous:
            raise ValueError('unordered_bars')
        previous = stamp
        if stamp < opened or stamp >= closed:
            outside += 1
            continue
        values = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
        o, h, l, c = values
        if (stamp.second or stamp.microsecond or
                not all(math.isfinite(v) and v > 0 for v in values) or
                h < max(o, l, c) or l > min(o, c)):
            raise ValueError('invalid_ohlc_or_timestamp')
        if stamp in selected:
            if selected[stamp] != row:
                raise ValueError('conflicting_duplicate')
            duplicates += 1
        else:
            selected[stamp] = row
    missing = [t.isoformat() for t in expected if t not in selected]
    return {'complete': not missing and len(selected) == len(expected),
            'expected_bars': len(expected), 'bars': len(selected),
            'missing_minutes': missing, 'identical_duplicates': duplicates,
            'outside_session_bars': outside,
            'history': {'time': [t.isoformat() for t in selected],
                        **{k: [r[k] for r in selected.values()]
                           for k in ('open', 'high', 'low', 'close')}}}


def write_json(path, payload):
    if shutil.disk_usage(path.parent).free < 256 * 1024 * 1024:
        raise RuntimeError('insufficient_disk_space')
    encoded = (json.dumps(payload, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(encoded)
    return hashlib.sha256(encoded).hexdigest()


def gateway(port, client_id):
    # Lazy imports allow calendar/validation tests without opening a connection.
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    from ibapi.contract import Contract

    class Reader(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready = threading.Event()
            self.done = threading.Event()
            self.active = None
            self.failure = None
            self.details = []
            self.rows = []
            self.bounds = None

        def nextValidId(self, orderId):
            self.ready.set()  # Handshake only; never request or place an order.

        def error(self, reqId, *args):
            # SDKs differ: (code, message, ...) or (errorTime, code, message, ...).
            code = args[0] if len(args) > 1 and isinstance(args[1], str) else args[1] if len(args) > 2 else None
            if reqId == self.active or code in (502, 504, 1100, 1300):
                self.failure = f'ibkr_error_code_{code}'
                self.done.set()

        def connectionClosed(self):
            self.failure = 'gateway_disconnected'
            self.done.set()

        def contractDetails(self, reqId, details):
            if reqId == self.active:
                self.details.append(details.contract)

        def contractDetailsEnd(self, reqId):
            if reqId == self.active:
                self.done.set()

        def historicalData(self, reqId, bar):
            if reqId == self.active:
                if len(self.rows) >= 1000:
                    self.failure = 'unexpected_batch_over_1000'
                    self.done.set()
                    return
                self.rows.append({'time': str(bar.date), 'open': bar.open,
                                  'high': bar.high, 'low': bar.low, 'close': bar.close,
                                  'volume': str(bar.volume)})

        def historicalDataEnd(self, reqId, start, end):
            if reqId == self.active:
                self.bounds = {'start': start, 'end': end}
                self.done.set()

        def wait(self):
            if not self.done.wait(60):
                raise RuntimeError('request_timeout')
            if self.failure:
                raise RuntimeError(self.failure)

        def begin(self, request_id):
            self.active = request_id
            self.failure = None
            self.done.clear()
            self.rows = []
            self.bounds = None

        def resolve(self):
            self.begin(101)
            contract = Contract()
            contract.symbol = 'SPX'
            contract.secType = 'IND'
            contract.exchange = 'CBOE'
            contract.currency = 'USD'
            self.reqContractDetails(self.active, contract)
            self.wait()
            matches = {c.conId: c for c in self.details
                       if c.symbol == 'SPX' and c.secType == 'IND'
                       and c.currency == 'USD' and c.exchange == 'CBOE' and c.conId > 0}
            if len(matches) != 1:
                raise RuntimeError('spx_contract_not_unique')
            return next(iter(matches.values()))

        def history(self, contract, close, request_id):
            self.begin(request_id)
            try:
                self.reqHistoricalData(request_id, contract, request_end(close),
                                       '1 D', '1 min', 'TRADES', 1, 2, False, [])
                self.wait()
                if self.bounds is None or not self.rows:
                    raise RuntimeError('missing_history')
                return list(self.rows), dict(self.bounds)
            finally:
                self.cancelHistoricalData(request_id)

    reader = Reader()
    try:
        reader.connect('127.0.0.1', port, clientId=client_id)
        threading.Thread(target=reader.run, daemon=True).start()
        if not reader.ready.wait(12):
            raise RuntimeError('gateway_handshake_timeout')
        return reader
    except Exception:
        reader.disconnect()
        raise


def collect(end, count, output, port=4001, client_id=20331025):
    planned = sessions(end, count)
    # A new directory prevents silent overwrite or mixing different acquisitions.
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    manifest = {'source': 'IBKR_TWS_API_HISTORY', 'live_feed_verified': False,
                'readiness': 'NOT_READY', 'requested_sessions': count,
                'notifications_enabled': False, 'orders_enabled': False,
                'sessions': []}
    reader = None
    try:
        reader = gateway(port, client_id)
        contract = reader.resolve()
        manifest['contract'] = {'symbol': 'SPX', 'security_type': 'IND',
                                'exchange': 'CBOE', 'currency': 'USD',
                                'contract_id': contract.conId}
        for index, (day, opened, closed) in enumerate(planned):
            if index:
                time.sleep(16)  # Sequential, below 60 historical requests / 10 min.
            rows, bounds = reader.history(contract, closed, 1000 + index)
            received = datetime.now(timezone.utc).isoformat()
            raw = {'contract': manifest['contract'], 'received_at': received,
                   'request': {'endDateTime': request_end(closed), 'durationStr': '1 D',
                               'barSizeSetting': '1 min', 'whatToShow': 'TRADES',
                               'useRTH': 1, 'formatDate': 2, 'keepUpToDate': False},
                   'provider_bounds': bounds, 'rows': rows}
            digest = write_json(output / f'{day}.raw.json', raw)
            result = validate_session(rows, opened, closed)
            history = result.pop('history')
            write_json(output / f'{day}.validated.json',
                       {'source': manifest['source'], 'received_at': received,
                        'contract': manifest['contract'], 'history': history,
                        'coverage': result})
            manifest['sessions'].append({'date': day, 'raw_sha256': digest, **result})
            print(f'{day}: {result["bars"]}/{result["expected_bars"]} bars; complete={result["complete"]}', flush=True)
        manifest['data_complete'] = all(s['complete'] for s in manifest['sessions'])
    except Exception as exc:
        # Do not persist provider text, authentication information or account IDs.
        manifest['data_complete'] = False
        known = str(exc)
        manifest['failure'] = known if (known.startswith('ibkr_error_code_') or known in {
            'request_timeout', 'gateway_disconnected', 'gateway_handshake_timeout',
            'spx_contract_not_unique', 'missing_history', 'unexpected_batch_over_1000',
            'unordered_bars', 'conflicting_duplicate', 'invalid_ohlc_or_timestamp',
            'insufficient_disk_space'}) else type(exc).__name__
    finally:
        if reader is not None:
            reader.disconnect()
        manifest['finished_at'] = datetime.now(timezone.utc).isoformat()
        write_json(output / 'manifest.json', manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--end', required=True, help='Last session date YYYY-MM-DD')
    parser.add_argument('--sessions', type=int, default=20)
    parser.add_argument('--output', required=True, help='New output directory')
    parser.add_argument('--port', type=int, default=4001)
    parser.add_argument('--client-id', type=int, default=20331025)
    args = parser.parse_args()
    report = collect(args.end, args.sessions, args.output, args.port, args.client_id)
    raise SystemExit(0 if report['data_complete'] else 2)


if __name__ == '__main__':
    main()
