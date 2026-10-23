from datetime import datetime, timedelta, timezone
import json
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from spx_availability_recorder import Trace, finalize, session_bounds, start_history_if_ready

UTC = timezone.utc


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.opened = datetime(2026, 10, 23, 13, 30, tzinfo=UTC)
        self.trace = Trace(self.root, '2026-10-23', self.opened,
                           self.opened + timedelta(minutes=3), now=self.opened-timedelta(minutes=1))
        self.trace.set_mode(1, now=self.opened)

    def tearDown(self):
        self.trace.close()
        self.directory.cleanup()

    def bar(self, minute, price=100.):
        return dict(time=int((self.opened+timedelta(minutes=minute)).timestamp()),
                    open=price, high=price+1, low=price-1, close=price+.5,
                    provider_time_raw=str(int((self.opened+timedelta(minutes=minute)).timestamp())),
                    volume_raw='-1')

    def test_backfill_and_clock_alone_never_establish_live_availability(self):
        self.trace.bar(self.bar(0), live=False, now=self.opened+timedelta(minutes=2))
        self.assertEqual(self.trace.coverage()['observed_minutes'], 0)
        self.trace.bar(self.bar(1), live=True, now=self.opened+timedelta(seconds=90))
        self.assertEqual(self.trace.coverage()['observed_minutes'], 0)
        self.assertFalse(self.trace.coverage()['full_prospective_trace'])

    def test_advancing_provider_preserves_prior_snapshot_and_receipt(self):
        self.trace.bar(self.bar(0), live=True, now=self.opened+timedelta(seconds=40))
        received = self.opened+timedelta(seconds=62)
        self.trace.bar(self.bar(1, 200.), live=True, now=received)
        first = self.trace.completed[self.bar(0)['time']]
        self.assertEqual(first['received_at'], received.isoformat())
        self.assertEqual(first['bar']['close'], 100.5)
        self.assertEqual(first['local_availability_lag_seconds'], 2)
        self.trace.bar(self.bar(0, 300.), live=True, now=received+timedelta(seconds=5))
        self.assertEqual(self.trace.completed[self.bar(0)['time']], first)
        self.assertFalse(first['bar_final_revision_verified'])

    def test_gap_missing_mode_and_midday_start_fail_full_trace(self):
        self.trace.bar(self.bar(0), live=True, now=self.opened+timedelta(seconds=10))
        self.trace.bar(self.bar(2), live=True, now=self.opened+timedelta(seconds=122))
        self.assertEqual(self.trace.coverage()['observed_minutes'], 1)
        self.assertIn(self.bar(1)['time'], self.trace.coverage()['missing_minutes'])
        self.trace.set_mode(3, now=self.opened+timedelta(seconds=130))
        self.trace.bar(self.bar(2), live=True, now=self.opened+timedelta(seconds=182))
        self.assertFalse(self.trace.coverage()['full_prospective_trace'])
        finalize(self.trace, self.root/'inputs', 4001)
        self.assertTrue((self.trace.folder/'partial.json').exists())
        self.assertFalse((self.root/'inputs').exists())

    def test_reconnect_cannot_upgrade_backfilled_preconnection_bar(self):
        self.trace.new_connection(now=self.opened+timedelta(seconds=95))
        self.trace.set_mode(1, now=self.opened+timedelta(seconds=96))
        self.trace.bar(self.bar(0), live=False, now=self.opened+timedelta(seconds=97))
        self.trace.bar(self.bar(0), live=True, now=self.opened+timedelta(seconds=98))
        self.trace.bar(self.bar(1), live=True, now=self.opened+timedelta(seconds=100))
        self.assertNotIn(self.bar(0)['time'], self.trace.completed)
        self.trace.bar(self.bar(2), live=True, now=self.opened+timedelta(seconds=122))
        self.assertIn(self.bar(1)['time'], self.trace.completed)

    def test_quotes_are_separate_and_full_coverage_is_not_backdated_on_resume(self):
        self.trace.quote(4, 100.5, now=self.opened+timedelta(seconds=10))
        self.trace.quote(45, str(int(self.opened.timestamp())), now=self.opened+timedelta(seconds=11))
        self.trace.quote(88, str(int(self.opened.timestamp())-900), now=self.opened+timedelta(seconds=12))
        for minute in range(3):
            self.trace.bar(self.bar(minute), live=True,
                           now=self.opened+timedelta(minutes=minute+1, seconds=2))
        self.assertTrue(self.trace.coverage()['full_prospective_trace'])
        events = [json.loads(line) for line in self.trace.path.read_text().splitlines()]
        quotes = [event for event in events if event['kind'] == 'quote_callback']
        self.assertEqual([event['tick_type'] for event in quotes], [4, 45, 88])
        self.assertTrue(all('price' not in event and 'trade_time' not in event for event in quotes))
        first = self.trace.completed[self.bar(0)['time']]
        self.trace.close()
        self.trace = Trace(self.root, '2026-10-23', self.opened,
                           self.opened+timedelta(minutes=3), now=self.opened+timedelta(minutes=5))
        self.assertEqual(self.trace.completed[self.bar(0)['time']], first)
        self.assertEqual(self.trace.started_at, self.opened-timedelta(minutes=1))
        last = json.loads(self.trace.path.read_text().splitlines()[-1])
        self.assertEqual(last['received_at'], (self.opened+timedelta(minutes=5)).isoformat())

    def test_mid_session_start_stays_partial_even_with_all_later_receipts(self):
        self.trace.started_at = self.opened+timedelta(seconds=10)
        for minute in range(3):
            self.trace.bar(self.bar(minute), live=True,
                           now=self.opened+timedelta(minutes=minute+1, seconds=2))
        self.assertEqual(self.trace.coverage()['observed_minutes'], 3)
        self.assertFalse(self.trace.coverage()['full_prospective_trace'])

    def test_nyse_dst_holiday_and_early_close(self):
        before = session_bounds('2026-10-30')
        after = session_bounds('2026-11-02')
        early = session_bounds('2026-11-27')
        self.assertEqual((before[0].hour, after[0].hour), (13, 14))
        self.assertEqual((early[1]-early[0]).total_seconds()/60, 210)
        self.assertIsNone(session_bounds('2026-11-26'))

    def complete_fixture(self):
        from collect_spx_sessions import request_end
        self.trace.contract_id = 416904
        for minute in range(3):
            self.trace.bar(self.bar(minute), live=True,
                           now=self.opened+timedelta(minutes=minute+1, seconds=2))
        contract = dict(symbol='SPX', security_type='IND', exchange='CBOE', currency='USD',
                        contract_id=416904)
        raw = dict(contract=contract,
                   received_at=(self.trace.closed_at+timedelta(minutes=1)).isoformat(),
                   provider_bounds={'start': 'original-start', 'end': 'original-end'},
                   request=dict(endDateTime=request_end(self.trace.closed_at), durationStr='1 D',
                                barSizeSetting='1 min', whatToShow='TRADES', useRTH=1,
                                formatDate=2, keepUpToDate=False),
                   rows=[self.bar(minute) for minute in range(3)])
        capture = self.root/'existing'
        capture.mkdir()
        encoded = json.dumps(raw).encode()
        path = capture/'2026-10-23.raw.json'
        path.write_bytes(encoded)
        manifest = dict(source='IBKR_TWS_API_HISTORY', contract=contract,
                        sessions=[dict(date='2026-10-23', raw_sha256=hashlib.sha256(encoded).hexdigest())])
        (capture/'manifest.json').write_text(json.dumps(manifest))
        return path

    def test_full_trace_reuses_hashed_daily_capture_without_network_or_overwrite(self):
        from unittest.mock import patch
        self.complete_fixture()
        with patch('collect_spx_sessions.collect') as collect:
            finalize(self.trace, self.root/'inputs', 4001)
            destination = self.root/'inputs/2026-10-23/raw.json'
            original = destination.read_bytes()
            result = json.loads(original)
            self.assertTrue(result['coverage']['full_prospective_trace'])
            self.assertEqual(len(result['first_completed_observations']), 3)
            self.assertEqual(result['daily_capture']['provider_bounds']['start'], 'original-start')
            finalize(self.trace, self.root/'inputs', 4001)
            self.assertEqual(destination.read_bytes(), original)
            collect.assert_not_called()

    def test_modified_daily_raw_is_rejected_before_publication(self):
        path = self.complete_fixture()
        path.write_bytes(path.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError, 'daily_capture_provenance_rejected'):
            finalize(self.trace, self.root/'inputs', 4001)
        self.assertFalse((self.root/'inputs/2026-10-23/raw.json').exists())

    def test_history_starts_once_only_after_live_open_provider_clock(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        client = SimpleNamespace(history_started=False, contract=object(), reqHistoricalData=Mock())
        self.assertFalse(start_history_if_ready(client, self.trace, self.opened-timedelta(seconds=1)))
        self.trace.quote(45, str(int((self.opened-timedelta(days=1)).timestamp())), now=self.opened)
        self.assertFalse(start_history_if_ready(client, self.trace, self.opened))
        self.trace.quote(45, str(int(self.opened.timestamp())), now=self.opened)
        self.trace.set_mode(3, now=self.opened)
        self.assertFalse(start_history_if_ready(client, self.trace, self.opened))
        self.trace.set_mode(1, now=self.opened)
        self.assertTrue(start_history_if_ready(client, self.trace, self.opened+timedelta(seconds=1)))
        self.assertFalse(start_history_if_ready(client, self.trace, self.opened+timedelta(seconds=2)))
        client.reqHistoricalData.assert_called_once()


if __name__ == '__main__':
    unittest.main()
