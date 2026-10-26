import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from collect_spx_daily import collect, normalize, plan, evaluate_capture
from collect_spx_sessions import gateway
from spx_daily import schedule


def fixture():
    dates=schedule('2024-10-28','2025-12-31').index
    return [dict(time=d.strftime('%Y%m%d'),open=5000,high=5010,low=4990,close=5002,volume='-1') for d in dates]


class Fake:
    def __init__(self,rows): self.rows=rows; self.calls=[];self.disconnected=False
    def resolve(self):
        return type('Contract',(),dict(conId=416904,symbol='SPX',secType='IND',exchange='CBOE',currency='USD'))()
    def daily_history(self,contract,close,request_id):
        self.calls.append((contract.conId,close.isoformat(),request_id))
        return self.rows,dict(start='provider start',end='provider end')
    def disconnect(self): self.disconnected=True


class DailyCollectorTests(unittest.TestCase):
    def test_evaluation_requires_validated_unchanged_capture(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'capture'
            with patch('collect_spx_daily.gateway',return_value=Fake(fixture())):
                collect('2024-10-28','2025-12-31',out,now='2026-01-01T00:00Z')
            original=(out/'input.json').read_bytes()
            (out/'input.json').write_bytes(original+b' ')
            with patch('evaluate_spx_daily.evaluate') as model:
                with self.assertRaisesRegex(ValueError,'hash mismatch'):evaluate_capture(out)
                model.assert_not_called()
            (out/'input.json').write_bytes(original)
            with patch('evaluate_spx_daily.evaluate',return_value=dict(status='NOT_READY')) as model:
                self.assertEqual(evaluate_capture(out)['status'],'NOT_READY')
                self.assertEqual(model.call_args.args[1:],('2025-04-01','2025-07-01'))
                with self.assertRaises(FileExistsError):evaluate_capture(out)
                self.assertEqual(model.call_count,1)

    def test_valid_export_is_bounded_hashed_and_read_only(self):
        rows=fixture();fake=Fake(rows)
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'capture'
            with patch('collect_spx_daily.gateway',return_value=fake):
                result=collect('2024-10-28','2025-12-31',out,now='2026-01-01T00:00Z')
            self.assertTrue(result['data_complete'])
            self.assertFalse(result['orders_enabled'])
            self.assertFalse(result['live_feed_verified'])
            self.assertEqual(fake.calls,[(416904,'2025-12-31T21:00:00+00:00',2101)])
            self.assertTrue(fake.disconnected)
            doc=json.loads((out/'input.json').read_text())
            self.assertEqual(doc['bars'][0]['open'],rows[0]['open'])
            self.assertEqual(doc['raw_sha256'],hashlib.sha256((out/'raw.json').read_bytes()).hexdigest())
            with self.assertRaises(FileExistsError):collect('2024-10-28','2025-12-31',out,now='2026-01-01T00:00Z')

    def test_bad_ohlc_and_gap_keep_raw_and_do_not_emit_input(self):
        for bad in ('ohlc','gap','identity'):
            rows=fixture()
            if bad=='ohlc': rows[10]['close']=5020
            if bad=='gap': del rows[10]
            fake=Fake(rows)
            if bad=='identity': fake.resolve=lambda:type('Contract',(),dict(conId=123,symbol='ES',secType='FUT',exchange='CME',currency='USD'))()
            with tempfile.TemporaryDirectory() as root:
                out=Path(root)/'capture'
                with patch('collect_spx_daily.gateway',return_value=fake):
                    report=collect('2024-10-28','2025-12-31',out,now='2026-01-01T00:00Z')
                self.assertEqual(report['status'],'WAIT_VALID_DATA')
                self.assertFalse((out/'input.json').exists())
                self.assertTrue(fake.disconnected)
                self.assertEqual((out/'raw.json').exists(),bad!='identity')

    def test_dates_never_reordered_and_incomplete_end_rejected(self):
        rows=fixture()
        for changed in ([rows[1],rows[0],*rows[2:]],[rows[0],*rows]):
            with self.assertRaises(ValueError):normalize(changed,'2024-10-28','2025-12-31')
        with self.assertRaises(ValueError):plan('2024-10-28','2025-12-31','2025-12-31T20:59Z')
        with self.assertRaises(ValueError):plan('2024-10-27','2025-12-31','2026-01-01T00:00Z')

    def test_daily_request_format_and_cancel_on_error(self):
        def ready(self,*args,**kwargs):self.ready.set()
        with patch('ibapi.client.EClient.connect',autospec=True,side_effect=ready), patch('collect_spx_sessions.threading.Thread.start'):
            reader=gateway(4001,999)
        def complete():
            reader.rows=[dict(time='20251231')];reader.bounds=dict(start='a',end='b')
        with patch.object(reader,'reqHistoricalData') as request, patch.object(reader,'cancelHistoricalData') as cancel, patch.object(reader,'wait',side_effect=complete):
            reader.daily_history(object(),schedule('2025-12-31','2025-12-31').iloc[0].market_close,2101)
            self.assertEqual(request.call_args.args[2:],('20251231-21:00:00','2 Y','1 day','TRADES',1,1,False,[]))
            cancel.assert_called_once_with(2101)
        with patch.object(reader,'reqHistoricalData'), patch.object(reader,'cancelHistoricalData') as cancel, patch.object(reader,'wait',side_effect=RuntimeError('timeout')):
            with self.assertRaises(RuntimeError):reader.daily_history(object(),schedule('2025-12-31','2025-12-31').iloc[0].market_close,2102)
            cancel.assert_called_once_with(2102)
        reader.disconnect()
