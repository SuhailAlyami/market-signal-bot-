from datetime import datetime,timezone,timedelta
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
import pandas as pd

from spx_primary import supporting_frame,index_frame,option_candidate,write_status
from hunter_runtime import validate_completed_bars
from github_signal_delivery import recommendation


class SPXTests(unittest.TestCase):
    def test_transient_windows_status_lock_retries_and_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            real_replace=Path.replace
            attempts=[]
            def replace(path,target):
                attempts.append(1)
                if len(attempts)<3:raise PermissionError('fixture sharing violation')
                return real_replace(path,target)
            with patch.object(Path,'replace',replace), patch('spx_primary.time.sleep'):
                self.assertTrue(write_status(root,{'status':'ok'}))
            self.assertEqual(len(attempts),3)
            self.assertEqual(json.loads((root/'status.json').read_text()),{'status':'ok'})

    def test_persistent_status_lock_keeps_previous_evidence_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'status.json').write_text('{"status":"old"}')
            with patch.object(Path,'replace',side_effect=PermissionError('fixture')), patch('spx_primary.time.sleep'):
                self.assertFalse(write_status(root,{'status':'ok'}))
            self.assertEqual(json.loads((root/'status.json').read_text()),{'status':'old'})

    def test_native_index_has_no_fabricated_volume(self):
        now=datetime(2026,10,22,15,tzinfo=timezone.utc)
        index=pd.date_range(end=now-timedelta(minutes=1),periods=32,freq='min')
        frame=pd.DataFrame({'Open':100.,'High':101.,'Low':99.,'Close':100.},index=index)
        frame.attrs.update(symbol='SPX',security_type='IND',source='IBKR Gateway TWS API')
        result,status=validate_completed_bars(frame,now)
        self.assertEqual(status['status'],'ok');self.assertNotIn('Volume',result)

    def test_helper_volume_is_actual_previous_es_minute_and_prices_unchanged(self):
        index=pd.date_range('2026-10-22T14:00Z',periods=34,freq='min')
        spx=pd.DataFrame({'Open':7000.,'High':7001.,'Low':6999.,'Close':7000.},index=index)
        es=pd.DataFrame({'Volume':range(100,134)},index=index)
        derived=supporting_frame(spx,es)
        self.assertEqual(derived.index[0],index[1]);self.assertEqual(derived.iloc[0].Volume,100)
        self.assertTrue((derived.Close==7000).all())
        self.assertIn('not SPX volume',derived.attrs['volume_source'])

    def test_live_type_without_index_timestamp_cannot_qualify(self):
        client=SimpleNamespace(lost=False,isConnected=lambda:True,types={201:1},quotes={201:[{'type':4,'price':7000}]})
        with self.assertRaisesRegex(RuntimeError,'timestamp_missing'):index_frame(client)

    def test_missing_spx_option_or_wrong_underlying_never_publishes(self):
        now=datetime(2026,10,22,15,tzinfo=timezone.utc);t=now.isoformat()
        event=dict(symbol='SPX',state='TRIGGER',signal_status='COMPLETE',notify_eligible=True,
            direction='UP',bar_end=t,detected_at=t,event_id='fixture',entry_zone=[7000,7001],stop_loss=6999,
            targets=[7002,7003],reason='fixture')
        heartbeat={'status':'ok','timestamp':t,'symbols':{'SPX':{'status':'ok','live_feed_verified':True,
            'feed_metadata':{'source':'IBKR Gateway TWS API','market_data_type':1,'last_trade_time':t,'last_price':7000.5}}}}
        self.assertIsNone(recommendation(event,heartbeat,now)[0])
        event['option_contract']={'symbol':'SPX','market_data_type':1,'live_verified':True,'right':'C',
            'contract_id':123,'expiry':'2026-10-22','strike':7000.,'bid':10.,'ask':10.5,'quote_time':t,'source':'fixture'}
        message,reason=recommendation(event,heartbeat,now)
        self.assertIsNone(reason);self.assertIn('SPX',message['title']);self.assertIn('Bid: 10.0',message['body'])
        event['option_contract']['quote_time']=(now-timedelta(seconds=11)).isoformat()
        self.assertIsNone(recommendation(event,heartbeat,now)[0])

    def test_initial_option_snapshot_is_not_verified_streaming_book(self):
        now=datetime.now(timezone.utc)
        contract=SimpleNamespace(lastTradeDateOrContractMonth='20261022',right='C',strike=7000,conId=123)
        client=SimpleNamespace(options={210:contract},types={210:1},quotes={210:[
            {'type':1,'price':10.,'received_at':now.isoformat()},
            {'type':2,'price':10.5,'received_at':now.isoformat()}]})
        frame=pd.DataFrame();frame.attrs.update(last_price=7000,last_trade_time=now.isoformat())
        self.assertIsNone(option_candidate(client,frame,'UP',now))


class PineSyncTests(unittest.TestCase):
    def test_rule_source_fingerprint_must_be_updated_with_pine(self):
        root=Path(__file__).resolve().parents[1]
        files=['strategy_rules.py','hunter_runtime.py','es_signal_plan.py','spx_primary.py','price_action_context.py']
        digest=hashlib.sha256(''.join((root/f).read_text(encoding='utf-8') for f in files).encode()).hexdigest()
        pine=(root/'tradingview/Suhail_Hunter_ES.pine').read_text(encoding='utf-8')
        self.assertIn('// PYTHON_RULE_SHA256: '+digest,pine)
        self.assertTrue(pine.startswith('//@version=6'))
        self.assertIn('barstate.isconfirmed',pine)
        self.assertIn('SPX WATCH; option contract unverified',pine)
