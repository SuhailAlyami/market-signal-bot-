import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

from verify_ibkr_capture import verify
from ibkr_market_data import normalize


class ConnectedCaptureTests(unittest.TestCase):
    def setUp(self):
        self.capture=json.loads((Path(__file__).resolve().parents[1]/'artifacts/ibkr-connected-20261020/capture.json').read_text())

    def test_retained_real_history_has_valid_ohlcv_and_explicit_snapshot_status(self):
        for symbol in ('ES','NQ'):
            record=self.capture['symbols'][symbol]
            self.assertEqual(record['snapshot']['top-status']['status'],'REALTIME')
            self.assertGreater(len(normalize(record['history'])),900)
            self.assertEqual(record['contract']['contract_month'],'202612')

    def test_stale_saved_capture_cannot_be_replayed_as_a_new_detection(self):
        with tempfile.TemporaryDirectory() as output:
            with patch('verify_ibkr_capture.run_once',side_effect=AssertionError('no late detection')):
                result=verify(self.capture,output,now='2026-10-20T10:00:00Z')
        self.assertEqual(result['status'],'STALE_OR_UNVERIFIED_INPUT_REJECTED')
        self.assertEqual(result['events'],[])
        self.assertFalse(result['capture_is_autonomous_runtime_authorization'])

    def test_future_receipts_rejected(self):
        data=copy.deepcopy(self.capture)
        data['symbols']['ES']['received_at']='2026-10-21T08:00:00Z'
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaises(ValueError):verify(data,output,now='2026-10-20T10:00:00Z')

    def test_naive_processing_clock_rejected(self):
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaises(ValueError):verify(self.capture,output,now='2026-10-20T08:38:26')

    def test_detector_receives_processing_clock_not_quote_timestamp(self):
        now=pd.Timestamp('2026-10-20T08:38:26.061691Z')
        with tempfile.TemporaryDirectory() as output:
            with patch('verify_ibkr_capture.run_once',return_value={'heartbeat':{'status':'ok'},'events':[]}) as run:
                result=verify(self.capture,output,now=now)
        self.assertEqual(run.call_args.kwargs['now'],now.to_pydatetime())
        self.assertEqual(result['status'],'VERIFIED_CAPTURE_ANALYZED')
        self.assertFalse(result['orders_enabled'])
