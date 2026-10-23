"""Prospective native SPX callback trace. Observation only; no signal/account/order API."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

UTC = timezone.utc
MODES = {1: 'REALTIME', 2: 'FROZEN', 3: 'DELAYED', 4: 'DELAYED_FROZEN'}


class RequestRejected(RuntimeError):
    pass


def utcnow():
    return datetime.now(UTC)


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(.05)


def session_bounds(day):
    import pandas_market_calendars as mcal
    table = mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day)
    if table.empty:
        return None
    row = table.iloc[0]
    return row.market_open.to_pydatetime(), row.market_close.to_pydatetime()


class Trace:
    def __init__(self, root, day, opened, closed, now=None):
        self.folder = Path(root) / day
        self.folder.mkdir(parents=True, exist_ok=True)
        self.day, self.opened, self.closed_at = day, opened, closed
        self.started_at = now or utcnow()
        self.connection_started_at = now or utcnow()
        self.completed = {}
        self.corrupt = False
        self.contract_id = None
        self.mode = None
        self.previous_live = None
        self.provider_clock = None
        self.last_update_at = None
        self.lock = threading.RLock()
        self.path = self.folder / 'events.jsonl'
        if self.path.exists():
            # Recover the first observations without overwriting an earlier receipt.
            with self.path.open(encoding='utf-8') as stream:
                for line in stream:
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeError):
                        self.corrupt = True
                        continue
                    if event.get('kind') == 'start':
                        self.started_at = min(self.started_at, datetime.fromisoformat(event['received_at']))
                    elif event.get('kind') == 'first_completed_observation':
                        self.completed.setdefault(event['bar']['time'], event)
                    elif event.get('kind') == 'subscriptions':
                        self.contract_id = event.get('contract_id')
            with self.path.open('rb') as stream:
                stream.seek(-1, 2) if self.path.stat().st_size else None
                tail = stream.read()
            if tail and tail != b'\n':
                with self.path.open('ab') as stream:
                    stream.write(b'\n')
                self.corrupt = True
        self.stream = self.path.open('a', encoding='utf-8', buffering=1)
        self.connection = uuid.uuid4().hex
        self.emit('start', now=now or utcnow(),
                  source='IBKR_TWS_API_HISTORY_KEEP_UP_TO_DATE', symbol='SPX',
                  security_type='IND', exchange='CBOE', currency='USD',
                  session_open=opened.isoformat(), session_close=closed.isoformat(),
                  resumed_with_corrupt_log=self.corrupt)

    def emit(self, kind, now=None, **fields):
        event = dict(kind=kind, received_at=(now or utcnow()).isoformat(),
                     receipt_monotonic_ns=time.monotonic_ns(), connection=self.connection, **fields)
        with self.lock:
            self.stream.write(json.dumps(event, allow_nan=False) + '\n')
        return event

    def new_connection(self, now=None):
        with self.lock:
            self.connection = uuid.uuid4().hex
            self.mode = self.previous_live = self.provider_clock = None
            self.last_update_at = None
            self.connection_started_at = now or utcnow()
            self.emit('connect_attempt', now=self.connection_started_at)

    def quote(self, tick_type, value, now=None):
        received = now or utcnow()
        # A provider clock and a price are distinct callbacks, never a joined trade.
        self.emit('quote_callback', now=received, tick_type=tick_type, value=value,
                  parallel_quote_mode=self.mode)
        if tick_type == 45:
            try:
                stamp = int(value)
                if stamp > 0:
                    self.provider_clock = dict(provider_time=stamp, received_at=received.isoformat())
            except (ValueError, TypeError):
                pass

    def set_mode(self, mode, now=None):
        self.mode = mode if mode in MODES else None
        self.emit('market_data_type', now=now, market_data_type=self.mode,
                  classification=MODES.get(mode, 'UNKNOWN'), scope='parallel_SPX_quote_subscription')

    def _complete(self, row, received, method):
        start = row['time']
        if start in self.completed or not self.opened.timestamp() <= start < self.closed_at.timestamp():
            return
        if received.timestamp() < start + 60:
            return
        if start + 60 < self.connection_started_at.timestamp():
            return  # Completed before this connection: original availability is unknown.
        event = self.emit('first_completed_observation', now=received, bar=dict(row),
                          provider_bar_end=start + 60, completion_evidence=method,
                          parallel_quote_mode=self.mode,
                          quote_classification=MODES.get(self.mode, 'UNKNOWN'),
                          bar_final_revision_verified=False,
                          local_availability_lag_seconds=received.timestamp() - start - 60)
        self.completed[start] = event

    def bar(self, row, *, live, now=None):
        received = now or utcnow()
        with self.lock:
            self.emit('historical_update' if live else 'historical_backfill', now=received,
                      bar=dict(row), parallel_quote_mode=self.mode)
            if not live:
                return  # Backfill receipt cannot establish original live availability.
            start = row['time']
            prices = [row[k] for k in ('open', 'high', 'low', 'close')]
            if (start % 60 or not all(math.isfinite(v) and v > 0 for v in prices)
                    or row['high'] < max(prices) or row['low'] > min(prices)):
                self.emit('invalid_bar', now=received)
                return
            self.last_update_at = received
            old = self.previous_live
            if old is not None and start > old['time']:
                self._complete(old, received, 'provider_advanced_to_later_bar')
                if start > old['time'] + 60:
                    self.emit('provider_bar_gap', now=received,
                              previous_start=old['time'], next_start=start)
            self._complete(row, received, 'live_update_received_after_bar_end')
            if old is None or start >= old['time']:
                self.previous_live = dict(row)
            else:
                self.emit('late_bar_revision', now=received, bar=dict(row))

    def coverage(self):
        expected = set(range(int(self.opened.timestamp()), int(self.closed_at.timestamp()), 60))
        observed = set(self.completed) & expected
        realtime = {stamp for stamp in observed if self.completed[stamp]['parallel_quote_mode'] == 1}
        complete = (self.started_at <= self.opened and not self.corrupt
                    and observed == expected and realtime == expected)
        return dict(day=self.day, expected_minutes=len(expected), observed_minutes=len(observed),
                    realtime_quote_mode_minutes=len(realtime), missing_minutes=sorted(expected-observed),
                    started_before_open=self.started_at <= self.opened,
                    full_prospective_trace=complete, corrupt_log=self.corrupt,
                    provider_clock=self.provider_clock,
                    last_update_at=self.last_update_at.isoformat() if self.last_update_at else None,
                    readiness='NOT_READY', orders_enabled=False, notifications_enabled=False)

    def close(self):
        self.stream.close()


def make_client(trace):
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper

    class Client(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.ready, self.resolved = threading.Event(), threading.Event()
            self.contracts, self.failed, self.fatal = [], False, None

        def placeOrder(self, *args, **kwargs):
            raise PermissionError('Orders are forbidden')

        def nextValidId(self, value):
            self.ready.set()

        def managedAccounts(self, value):
            pass

        def contractDetails(self, reqId, details):
            if reqId == 101:
                self.contracts.append(details.contract)

        def contractDetailsEnd(self, reqId):
            if reqId == 101:
                self.resolved.set()

        def error(self, reqId, *args):
            code = args[0] if len(args) > 1 and isinstance(args[1], str) else args[1] if len(args) > 2 else None
            trace.emit('api_error', request_id=reqId, code=code)
            if reqId in (101, 201, 301) and code not in (2104, 2106, 2158):
                self.fatal = code
                self.resolved.set()
            if code in (502, 504, 1100, 1300):
                self.failed = True

        def connectionClosed(self):
            self.failed = True
            trace.emit('connection_closed')

        def marketDataType(self, reqId, mode):
            if reqId == 201:
                trace.set_mode(mode)

        def tickString(self, reqId, tickType, value):
            if reqId == 201 and tickType in (45, 88):
                trace.quote(tickType, value)

        def tickPrice(self, reqId, tickType, price, attrib):
            if reqId == 201 and tickType == 4:
                trace.quote(tickType, price)

        def record_bar(self, reqId, bar, live):
            if reqId != 301:
                return
            received = utcnow()
            try:
                row = dict(time=int(bar.date), provider_time_raw=str(bar.date),
                           **{k: float(getattr(bar, k)) for k in ('open', 'high', 'low', 'close')},
                           volume_raw=str(bar.volume))
                trace.bar(row, live=live, now=received)
            except (ValueError, TypeError, OverflowError):
                trace.emit('invalid_provider_bar', now=received)

        def historicalData(self, reqId, bar):
            self.record_bar(reqId, bar, False)

        def historicalDataUpdate(self, reqId, bar):
            self.record_bar(reqId, bar, True)

        def historicalDataEnd(self, reqId, start, end):
            trace.emit('initial_history_end', provider_bounds=dict(start=start, end=end))

    return Client()


def subscribe(trace, port, client_id):
    from ibapi.contract import Contract
    trace.new_connection()
    client = make_client(trace)
    try:
        client.connect('127.0.0.1', port, clientId=client_id)
        client.thread = threading.Thread(target=client.run, daemon=True)
        client.thread.start()
        if not client.ready.wait(12):
            raise RuntimeError('gateway_handshake_timeout')
        contract = Contract()
        contract.symbol, contract.secType, contract.exchange, contract.currency = 'SPX', 'IND', 'CBOE', 'USD'
        client.reqContractDetails(101, contract)
        if not client.resolved.wait(30):
            raise RuntimeError('contract_timeout')
        matches = {c.conId: c for c in client.contracts if c.symbol == 'SPX' and c.secType == 'IND'
                   and c.exchange == 'CBOE' and c.currency == 'USD' and c.conId > 0}
        if client.fatal is not None:
            raise RequestRejected(str(client.fatal))
        if len(matches) != 1:
            raise RequestRejected('spx_contract_not_unique')
        contract = next(iter(matches.values()))
        if trace.contract_id is not None and trace.contract_id != contract.conId:
            raise RequestRejected('spx_contract_identity_changed')
        trace.contract_id = contract.conId
        trace.emit('subscriptions', contract_id=contract.conId, port=port,
                   parallel_quote_requested=True, history_started=False)
        client.contract, client.history_started = contract, False
        client.reqMarketDataType(1)
        client.reqMktData(201, contract, '', False, False, [])
        client.connected_at = time.monotonic()
        return client
    except Exception:
        disconnect(client)
        raise


def disconnect(client):
    client.disconnect()
    thread = getattr(client, 'thread', None)
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=5)


def start_history_if_ready(client, trace, now):
    if client.history_started or not trace.opened <= now < trace.closed_at or trace.mode != 1:
        return False
    clock = trace.provider_clock
    if clock is None or not trace.opened.timestamp() <= clock['provider_time'] <= now.timestamp():
        return False
    if now.timestamp()-clock['provider_time'] > 10:
        return False
    # Quote stream is established first. No repeated empty pre-open history calls.
    trace.connection_started_at = now
    trace.emit('historical_subscription', now=now,
               request=dict(durationStr='7200 S', barSizeSetting='1 min', whatToShow='TRADES',
                            useRTH=1, formatDate=2, keepUpToDate=True))
    client.reqHistoricalData(301, client.contract, '', '7200 S', '1 min', 'TRADES', 1, 2, True, [])
    client.history_started, client.history_started_at = True, time.monotonic()
    return True


@contextmanager
def recorder_lock(root):
    path = root / 'recorder.lock'
    with path.open('a+b') as stream:
        stream.seek(0)
        if path.stat().st_size == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def finalize(trace, publish_root, port):
    """One final daily acquisition only for a fully observed prospective session."""
    from collect_spx_sessions import collect, request_end, validate_session
    coverage = trace.coverage()
    with trace.path.open('rb') as stream:
        coverage['trace_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
    if not coverage['full_prospective_trace']:
        atomic_json(trace.folder / 'partial.json', coverage)
        return
    existing = sorted(publish_root.parent.rglob(f'{trace.day}.raw.json'))
    capture = trace.folder / 'capture'
    if existing:
        raw_path = existing[0]  # Reuse byte-identical recorded input; never recollect it.
    else:
        if not capture.exists():
            collect(trace.day, 1, capture, port, 20331028)
        raw_path = capture / f'{trace.day}.raw.json'
    if not raw_path.exists():
        coverage['failure'] = 'daily_capture_missing_no_unchanged_retry'
        atomic_json(trace.folder / 'partial.json', coverage)
        return
    encoded = raw_path.read_bytes()
    raw = json.loads(encoded)
    expected_contract = dict(symbol='SPX', security_type='IND', exchange='CBOE',
                             currency='USD', contract_id=trace.contract_id)
    if raw.get('contract') != expected_contract:
        raise ValueError('daily_capture_identity_mismatch')
    expected_request = dict(endDateTime=request_end(trace.closed_at), durationStr='1 D',
                            barSizeSetting='1 min', whatToShow='TRADES', useRTH=1,
                            formatDate=2, keepUpToDate=False)
    received = datetime.fromisoformat(raw['received_at'])
    manifest = json.loads((raw_path.parent / 'manifest.json').read_text(encoding='utf-8'))
    digest = hashlib.sha256(encoded).hexdigest()
    if (raw.get('request') != expected_request or received.tzinfo is None
            or received < trace.closed_at or not raw.get('provider_bounds', {}).get('start')
            or not raw.get('provider_bounds', {}).get('end')
            or manifest.get('source') != 'IBKR_TWS_API_HISTORY'
            or manifest.get('contract') != expected_contract
            or not any(s.get('date') == trace.day and s.get('raw_sha256') == digest
                       for s in manifest.get('sessions', []))):
        raise ValueError('daily_capture_provenance_rejected')
    final = validate_session(raw['rows'], trace.opened, trace.closed_at)
    if not final['complete']:
        coverage['failure'] = 'daily_capture_incomplete_no_unchanged_retry'
        atomic_json(trace.folder / 'partial.json', coverage)
        return
    destination = publish_root / trace.day / 'raw.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        return
    value = dict(source='NATIVE_SPX_PROSPECTIVE_AVAILABILITY_DIAGNOSTIC',
                 data_role='CONSUMED_AVAILABILITY_DEVELOPMENT_NOT_SIGNAL_HOLDOUT',
                 contract=expected_contract, coverage=coverage,
                 original_event_log=str(trace.path), original_event_log_sha256=coverage['trace_sha256'],
                 daily_capture_sha256=hashlib.sha256(encoded).hexdigest(), daily_capture=raw,
                 first_completed_observations=list(trace.completed.values()),
                 quote_timestamp_semantics='Separate original callbacks in event log; not joined trades',
                 source_finality='Live snapshots may differ from final historical revision',
                 readiness='NOT_READY', notifications_enabled=False, orders_enabled=False)
    atomic_json(destination, value)
    atomic_json(trace.folder / 'complete.json', coverage)


def run(state, publish_root, port, client_id):
    from zoneinfo import ZoneInfo
    state.mkdir(parents=True, exist_ok=True)
    client = trace = None
    day = None
    bounds = None
    retries, next_attempt, blocked = 0, 0., False
    with recorder_lock(state):
        # Resume a trace interrupted after close without recollecting an attempted day.
        for folder in sorted(state.iterdir()):
            try:
                past = datetime.strptime(folder.name, '%Y-%m-%d').date().isoformat()
            except ValueError:
                continue
            if (not folder.is_dir() or not (folder / 'events.jsonl').exists()
                    or (folder / 'complete.json').exists() or (folder / 'partial.json').exists()):
                continue
            old_bounds = session_bounds(past)
            if old_bounds and utcnow() >= old_bounds[1] + timedelta(minutes=5):
                old = Trace(state, past, *old_bounds)
                finalize(old, publish_root, port)
                old.close()
        while not (state / 'STOP').exists():
            now = utcnow()
            today = now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
            if today != day:
                if trace is not None:
                    if client is not None:
                        disconnect(client)
                        client = None
                    finalize(trace, publish_root, port)
                    trace.close()
                    trace = None
                day, bounds, blocked, retries = today, session_bounds(today), False, 0
                next_attempt = 0
            active = bounds and bounds[0] - timedelta(minutes=5) <= now < bounds[1] + timedelta(minutes=5)
            if not active:
                if client is not None:
                    client.cancelHistoricalData(301)
                    client.cancelMktData(201)
                    disconnect(client)
                    client = None
                if trace is not None:
                    finalize(trace, publish_root, port)
                    trace.close()
                    trace = None
                atomic_json(state / 'status.json', dict(status='waiting_session', observed_at=now.isoformat(),
                                                       day=day, readiness='NOT_READY'))
                time.sleep(30)
                continue
            if trace is None:
                trace = Trace(state, day, *bounds, now=now)
            if client is not None and client.fatal is not None:
                trace.emit('request_blocked_no_retry_this_session', code=client.fatal)
                blocked = True
                disconnect(client)
                client = None
            history_stale = (client is not None and client.history_started
                             and trace.opened <= now < trace.closed_at
                             and time.monotonic()-client.history_started_at > 60
                             and (trace.last_update_at is None or
                                  (now-trace.last_update_at).total_seconds() > 60))
            if client is not None and (client.failed or not client.isConnected()
                                       or not client.thread.is_alive() or history_stale):
                trace.emit('data_connection_outage', history_stale=history_stale)
                disconnect(client)
                client = None
                retries += 1
                next_attempt = time.monotonic() + min(300, 15 * 2 ** min(retries, 5))
            if client is None and not blocked and time.monotonic() >= next_attempt:
                try:
                    client = subscribe(trace, port, client_id)
                    retries = 0
                except RequestRejected as exc:
                    blocked = True
                    trace.emit('request_blocked_no_retry_this_session', code=str(exc))
                except Exception as exc:
                    retries += 1
                    next_attempt = time.monotonic() + min(300, 15 * 2 ** min(retries, 5))
                    trace.emit('connect_failed', error_type=type(exc).__name__)
            if client is not None:
                start_history_if_ready(client, trace, utcnow())
            status = trace.coverage()
            status_now = utcnow()
            healthy_history = (trace.last_update_at is not None
                               and 0 <= (status_now-trace.last_update_at).total_seconds() <= 20)
            status.update(observed_at=status_now.isoformat(), recorder_pid=os.getpid(),
                          status='request_blocked' if blocked else 'reconnecting' if client is None
                          else 'recording' if healthy_history else 'waiting_or_stale_history')
            atomic_json(state / 'status.json', status)
            time.sleep(5)
        if client is not None:
            disconnect(client)
        if trace is not None:
            trace.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--publish-root', type=Path, required=True)
    parser.add_argument('--port', type=int, default=4001)
    parser.add_argument('--client-id', type=int, default=20331027)
    args = parser.parse_args()
    run(args.state, args.publish_root, args.port, args.client_id)


if __name__ == '__main__':
    main()
