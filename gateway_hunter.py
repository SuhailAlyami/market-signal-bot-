"""Local, market-data-only Gateway adapter for the canonical HunterRuntime.

No order/account API is exposed by this adapter. Experimental signals stay shadow.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
import urllib.parse
import urllib.request

import pandas as pd
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract

from hunter_runtime import HunterRuntime

UTC = timezone.utc
SOURCE = 'IBKR Gateway TWS API'


def stamp():
    return datetime.now(UTC).isoformat()


@contextmanager
def reader_lock(directory):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    stream = (directory/'.reader.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if stream.seek(0, 2) == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        stream.close()


class DataClient(EWrapper, EClient):
    def __init__(self):
        EWrapper.__init__(self)
        EClient.__init__(self, self)
        self.ready = threading.Event()
        self.history_ready = threading.Event()
        self.contract_ready = threading.Event()
        self.lock = threading.RLock()
        self.rows = {}
        self.contracts = []
        self.kind = None
        self.trade_time = 0
        self.received = 0
        self.tick_count = 0
        self.last_price = None
        self.lost = False
        self.errors = []

    def placeOrder(self, *args, **kwargs):
        raise PermissionError('Trading is forbidden')

    def managedAccounts(self, accountsList):
        pass

    def nextValidId(self, orderId):
        self.ready.set()

    def connectionClosed(self):
        self.lost = True

    def error(self, reqId, errorCode, errorString, *extra):
        with self.lock:
            self.errors.append({'time': stamp(), 'request_id': reqId, 'code': errorCode,
                                'message': errorString})
            self.errors = self.errors[-30:]
            if errorCode in (1100, 1101, 1102, 1300, 502, 504, 10225):
                self.lost = True

    def contractDetails(self, reqId, details):
        self.contracts.append(details.contract)

    def contractDetailsEnd(self, reqId):
        self.contract_ready.set()

    def marketDataType(self, reqId, kind):
        self.kind = kind

    def tickPrice(self, reqId, tickType, price, attrib):
        if price > 0:
            self.received = time.time()
            self.tick_count += 1
            if tickType == 4:
                self.last_price = price

    def tickString(self, reqId, tickType, value):
        if tickType == 45:
            try:
                self.trade_time = int(value)
                self.received = time.time()
            except ValueError:
                pass

    def _bar(self, bar):
        with self.lock:
            self.rows[int(bar.date)] = [bar.open, bar.high, bar.low, bar.close, bar.volume]
            for key in sorted(self.rows)[:-180]:
                del self.rows[key]

    def historicalData(self, reqId, bar):
        self._bar(bar)

    def historicalDataUpdate(self, reqId, bar):
        self._bar(bar)

    def historicalDataEnd(self, reqId, start, end):
        self.history_ready.set()

    def frame(self, symbol, now=None):
        now = time.time() if now is None else now
        if symbol not in ('ES', 'ES=F'):
            raise ValueError('Only ES is enabled')
        if self.lost or not self.isConnected():
            raise RuntimeError('gateway_disconnected')
        if self.kind != 1:
            raise RuntimeError('feed_not_realtime')
        if not (0 <= now-self.trade_time <= 60 and 0 <= now-self.received <= 60):
            raise RuntimeError('stale_quote')
        with self.lock:
            keys = sorted(self.rows)
            completed = [key for key in keys if key+60 <= now]
            # Fresh quotes do not prove that the independent bar subscription
            # is advancing. Rebuild the session rather than remain stuck forever.
            if not completed or now-(completed[-1]+60)>90:
                raise RuntimeError('stale_completed_bars')
            frame = pd.DataFrame([self.rows[k] for k in keys],
                index=pd.to_datetime(keys, unit='s', utc=True),
                columns=['Open', 'High', 'Low', 'Close', 'Volume'])
        frame.attrs.update(source=SOURCE, live_feed_verified=True,
                           observed_at=stamp(), market_data_type=self.kind,
                           last_trade_time=datetime.fromtimestamp(self.trade_time, UTC).isoformat(),
                           last_price=self.last_price,
                           bar_publication_latency_verified=False)
        return frame


def connect(client_id):
    client = DataClient()
    def run():
        try:
            client.connect('127.0.0.1', 4001, clientId=client_id)
            client.run()
        except Exception:
            client.lost = True
    threading.Thread(target=run, daemon=True).start()
    try:
        if not client.ready.wait(12):
            raise RuntimeError('api_handshake_timeout')
        contract = Contract()
        contract.symbol = 'ES'; contract.secType = 'FUT'
        contract.exchange = 'CME'; contract.currency = 'USD'
        client.reqContractDetails(101, contract)
        if not client.contract_ready.wait(12):
            raise RuntimeError('contract_timeout')
        today = datetime.now(UTC).strftime('%Y%m%d')
        valid = sorted((c for c in client.contracts if c.lastTradeDateOrContractMonth > today),
                       key=lambda c: c.lastTradeDateOrContractMonth)
        if not valid:
            raise RuntimeError('no_active_es_contract')
        client.contract = valid[0]
        client.reqMarketDataType(1)
        client.reqMktData(201, client.contract, '', False, False, [])
        client.reqHistoricalData(301, client.contract, '', '7200 S', '1 min',
                                 'TRADES', 0, 2, True, [])
        if not client.history_ready.wait(20):
            raise RuntimeError('history_timeout')
        return client
    except Exception:
        client.disconnect()
        raise


def send_test(directory, evidence):
    """An explicit TEST transport check, never a fabricated detector event."""
    marker = directory/'telegram-test.json'
    if marker.exists():
        return json.loads(marker.read_text(encoding='utf-8'))
    token = os.getenv('TELEGRAM_BOT_TOKEN', '')
    chat = os.getenv('TELEGRAM_CHAT_ID', '')
    if not token or not chat:
        return {'status': 'credentials_unavailable', 'time': stamp()}
    text = ('🧪 اختبار فقط — سهيل هنتر — ليس إشارة تداول\n'
            'نجح استقبال ES اللحظي عبر Gateway وربطه بمحرك الرصد وقت الفحص المسجل.\n'
            f"وقت إرسال الاختبار UTC: {stamp()}\n"
            f"وقت دليل البيانات UTC: {evidence.get('time', stamp())}\nTicks: {evidence['tick_count']}\n"
            'القراءة فقط؛ لم تنفذ أي صفقة. الاستراتيجية بحثية NOT READY.')
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage',
        data=urllib.parse.urlencode({'chat_id': chat, 'text': text}).encode())
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
        if not result.get('ok') or not result.get('result', {}).get('message_id'):
            raise ValueError('telegram_not_accepted')
        receipt = {'status': 'telegram_api_accepted', 'message_id': result['result']['message_id'],
                   'time': stamp(), 'human_read_verified': False}
        marker.write_text(json.dumps(receipt), encoding='utf-8')
        return receipt
    except Exception as exc:
        # Exception URLs can contain credentials: retain only exception class.
        return {'status': 'delivery_failed', 'error_type': type(exc).__name__, 'time': stamp()}


def monitor(directory, seconds=0, test_alert=False, reconnect_test_after=0, github_signals=False, relay_config=None,telegram_signals=False,spx_primary=False):
    directory = Path(directory); directory.mkdir(parents=True, exist_ok=True)
    runtime = HunterRuntime(directory/'state.json', directory/'shadow.jsonl', symbols=('ES=F',))
    client = None; started = time.monotonic(); retry_at = 0; failures = 0
    primary_stop=threading.Event()
    if spx_primary:
        from spx_primary import run as run_spx_primary
        def es_support():
            if client is None:raise RuntimeError('es_support_unavailable')
            return client.frame('ES')
        threading.Thread(target=run_spx_primary,args=(directory,es_support,primary_stop,github_signals,telegram_signals),daemon=True,name='spx-primary').start()
    last_status = None; injected = False; session_count = 0; alert_attempted = False
    def journal(item):
        with (directory/'connection.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'time': stamp(), **item})+'\n')
    try:
        while not seconds or time.monotonic()-started < seconds:
            if client is None and time.monotonic() >= retry_at:
                try:
                    client = connect(20331022)
                    session_count += 1
                    journal({'status': 'connected', 'session': session_count,
                             'contract_id': client.contract.conId})
                except Exception as exc:
                    failures += 1; retry_at = time.monotonic()+min(60, 2**min(failures, 6))
                    journal({'status': 'reconnect_failed', 'error_type': type(exc).__name__,
                             'reason': str(exc), 'retry_in_seconds': min(60,2**min(failures,6))})
            if client and reconnect_test_after and not injected and time.monotonic()-started >= reconnect_test_after:
                journal({'status': 'controlled_client_disconnect', 'test': True})
                client.disconnect(); client.lost = True; injected = True
            current = client
            def fetch(symbol):
                if current is None:
                    raise RuntimeError('gateway_unavailable')
                return current.frame(symbol)
            result = runtime.poll(datetime.now(UTC), fetch, clock=lambda: datetime.now(UTC))
            heartbeat = result['heartbeat']
            from github_signal_delivery import deliver
            outgoing = []
            delivery_heartbeat=heartbeat
            if relay_config and current:
                try:
                    from gateway_relay import push_frame
                    primary_status=None
                    primary_path=directory/'spx'/'status.json'
                    if spx_primary and primary_path.exists():
                        raw_status=json.loads(primary_path.read_text(encoding='utf-8'))
                        fields=('primary_symbol','support_symbol','status','blocker','time','index_data_type')
                        primary_status={k:raw_status[k] for k in fields if k in raw_status}
                        primary_status['sampled_option_count']=len(raw_status.get('sampled_options',[]))
                    relay=push_frame(current.frame('ES'),current.contract,relay_config['url'],relay_config['secret'],primary_status=primary_status)
                    delivery_heartbeat=relay['heartbeat']
                    if github_signals or telegram_signals: outgoing=relay['events']
                    journal({'event':'relay','status':relay['heartbeat']['status'],
                             'remote_timestamp':relay['heartbeat']['timestamp']})
                except Exception as exc:
                    journal({'event':'relay','status':'relay_unavailable','error_type':type(exc).__name__})
                    # Cloud operation is explicitly selected: no silent local fallback publication.
            elif (github_signals or telegram_signals) and current:
                from es_signal_plan import complete_plan
                for event in result['events']:
                    try:
                        plan,reason = complete_plan(event,current.frame('ES'))
                    except RuntimeError:
                        plan,reason = None,'feed_lost_before_plan'
                    if plan: outgoing.append(plan)
                    elif event.get('state')=='TRIGGER':
                        runtime.reject_plan(event,reason)
                        journal({'event':'signal_blocked','reason':reason,'event_id':event['event_id']})
            deliveries = deliver(outgoing, delivery_heartbeat, directory) if github_signals else []
            for delivery in deliveries:
                journal({'event': 'github_delivery', **delivery})
            if telegram_signals:
                try:
                    from telegram_signal_delivery import deliver as telegram_deliver,verify_once
                    verification=verify_once(directory,delivery_heartbeat)
                    if verification and verification['status']!='telegram_credentials_unavailable':
                        journal({'event':'telegram_verification',**verification})
                    for delivery in telegram_deliver(outgoing,delivery_heartbeat,directory):
                        journal({'event':'telegram_delivery',**delivery})
                except Exception as exc:
                    journal({'event':'telegram_delivery','status':'unavailable','error_type':type(exc).__name__})
            status = heartbeat['status']
            evidence = {'time': stamp(), 'status': status, 'source': SOURCE,
                        'sessions': session_count, 'orders_enabled': False,
                        'tick_count': client.tick_count if client else 0,
                        'last_trade_time': client.trade_time if client else None,
                        'market_data_type': client.kind if client else None,
                        'heartbeat': heartbeat}
            if status != last_status:
                journal({'status': status, 'previous': last_status})
                last_status = status
            if client and status == 'ok':
                failures = 0
                if test_alert and not alert_attempted:
                    evidence['telegram'] = send_test(directory, evidence)
                    journal({'event': 'telegram_test', **evidence['telegram']})
                    alert_attempted = True
            (directory/'heartbeat.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            journal({'status': 'sample', 'tick_count': evidence['tick_count'],
                     'last_trade_time': evidence['last_trade_time'], 'session': session_count})
            if client:
                try:
                    client.frame('ES')
                except RuntimeError as exc:
                    journal({'status': 'feed_unavailable', 'reason': str(exc), 'errors': client.errors})
                    client.disconnect(); client = None
                    failures += 1; retry_at = time.monotonic()+min(60,2**min(failures,6))
            time.sleep(5)
    finally:
        primary_stop.set()
        if client:
            client.disconnect()
        journal({'status': 'monitor_stopped'})
        path = directory/'heartbeat.json'
        if path.exists():
            stopped = json.loads(path.read_text(encoding='utf-8'))
            stopped.update(status='monitor_stopped', stopped_at=stamp())
            path.write_text(json.dumps(stopped, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', default='.hunter-state/gateway')
    parser.add_argument('--seconds', type=int, default=0, help='0 means continuous')
    parser.add_argument('--test-alert', action='store_true')
    parser.add_argument('--reconnect-test-after', type=int, default=0)
    parser.add_argument('--github-signals',action='store_true',help='Explicit opt-in to complete experimental ES rule alerts')
    parser.add_argument('--telegram-signals',action='store_true',help='Independent Telegram alerts using private local credentials')
    parser.add_argument('--spx-primary',action='store_true',help='Native SPX primary/options monitor; ES is auxiliary')
    parser.add_argument('--relay-config',type=Path,help='Private local generated relay configuration outside repo')
    args = parser.parse_args()
    relay_config=None
    if args.relay_config:
        from ibkr_mcp_client import _oauth_path_is_private
        if not _oauth_path_is_private(args.relay_config): raise PermissionError('Relay config must be private')
        relay_config=json.loads(args.relay_config.read_text(encoding='utf-8'))
    with reader_lock(args.state_dir):
        monitor(args.state_dir, args.seconds, args.test_alert, args.reconnect_test_after,args.github_signals,relay_config,args.telegram_signals,args.spx_primary)
