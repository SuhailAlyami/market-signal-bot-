from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest

from premium_shadow_outcomes import outcome, reconcile

NOW = datetime(2026, 10, 20, 14, 0, tzinfo=timezone.utc)


def event():
    return {'event_id': 'test-event', 'state': 'WATCH', 'detected_at': NOW.isoformat(),
            'reference_trade_price': 10., 'expiry': '2026-10-20', 'strike': 7695., 'side': 'CALL'}


def records():
    result = []
    for i in range(5):
        stamp = NOW+timedelta(minutes=i)
        result.append({'contract_id': 1, 'bar_start': stamp.isoformat(),
                       'received_at': (stamp+timedelta(minutes=1, seconds=10)).isoformat(),
                       'expiry': '2026-10-20', 'strike': 7695., 'side': 'CALL',
                       'open': 10., 'high': 13. if i == 3 else 10.2, 'low': 9.5,
                       'close': 10.1, 'volume': 100., 'feed_status': 'REALTIME', 'historical_delayed': 0})
    return result


class OutcomeTests(unittest.TestCase):
    def test_future_bars_only_and_no_execution_claim(self):
        rows = records()
        past = {**rows[0], 'bar_start': (NOW-timedelta(minutes=1)).isoformat(), 'high': 1000.}
        result = outcome(event(), [past]+rows, NOW+timedelta(minutes=6))
        self.assertEqual(result['status'], 'scored')
        self.assertTrue(result['target_hit'])
        self.assertAlmostEqual(result['max_trade_rise_pct'], 30.)
        self.assertAlmostEqual(result['max_trade_fall_pct'], -5.)
        self.assertIsNone(result['execution_price'])
        self.assertFalse(result['notifications_enabled'])

    def test_unseen_future_cannot_be_used(self):
        result = outcome(event(), records(), NOW+timedelta(minutes=4))
        self.assertEqual(result['status'], 'pending')
        self.assertIsNone(result['target_hit'])

    def test_partial_detection_minute_is_excluded(self):
        item = event()
        item['detected_at'] = (NOW+timedelta(seconds=30)).isoformat()
        rows = records()
        rows[0]['high'] = 1000.
        last = {**rows[-1], 'bar_start': (NOW+timedelta(minutes=5)).isoformat(),
                'received_at': (NOW+timedelta(minutes=6, seconds=10)).isoformat()}
        rows.append(last)
        result = outcome(item, rows, NOW+timedelta(minutes=7))
        self.assertEqual(result['status'], 'scored')
        self.assertEqual(result['window_start'], (NOW+timedelta(minutes=1)).isoformat())
        self.assertAlmostEqual(result['max_trade_rise_pct'], 30.)

    def test_first_version_survives_later_revision_even_if_list_reordered(self):
        rows = records()
        rows[3]['high'] = 10.2
        revision = {**rows[3], 'high': 1000.,
                    'received_at': (NOW+timedelta(minutes=6)).isoformat()}
        result = outcome(event(), [revision]+rows, NOW+timedelta(minutes=7))
        self.assertFalse(result['target_hit'])

    def test_missing_bars_censored_after_grace_never_automatic_loss(self):
        self.assertEqual(outcome(event(), records()[:-1], NOW+timedelta(minutes=6))['status'], 'pending')
        result = outcome(event(), records()[:-1], NOW+timedelta(minutes=8))
        self.assertEqual(result['status'], 'censored')
        self.assertIsNone(result['target_hit'])

    def test_delayed_frozen_invalid_and_zero_volume_censored(self):
        for change in ({'feed_status': 'FROZEN'}, {'historical_delayed': 1}, {'volume': 0.},
                       {'high': float('nan')}, {'low': -1.}, {'high': 9.}):
            rows = records()
            rows[0].update(change)
            with self.subTest(change=change):
                self.assertEqual(outcome(event(), rows, NOW+timedelta(minutes=6))['status'], 'censored')

    def test_bulk_historical_download_cannot_pose_as_timely_observation(self):
        rows = records()
        for row in rows:
            row['received_at'] = (NOW+timedelta(days=1)).isoformat()
        result = outcome(event(), rows, NOW+timedelta(days=1))
        self.assertEqual(result['reason'], 'late_delayed_or_unfinished_future_bar')
        self.assertIsNone(result['target_hit'])

    def test_contract_ambiguity_and_bad_clocks_rejected(self):
        rows = records()
        rows[0]['contract_id'] = 2
        self.assertEqual(outcome(event(), rows, NOW+timedelta(minutes=6))['reason'], 'ambiguous_contract_identity')
        with self.assertRaises(ValueError):
            outcome(event(), rows, NOW.replace(tzinfo=None))

    def test_restart_deduplication_and_cumulative_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'premium_shadow.jsonl').write_text(json.dumps(event())+'\n')
            (path/'premium_bars').mkdir()
            (path/'premium_bars/1-2026-10-20.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in records()))
            first = reconcile(directory, NOW+timedelta(minutes=6))
            second = reconcile(directory, NOW+timedelta(minutes=7))
            self.assertEqual(first, second)
            self.assertEqual(first['scored'], 1)
            self.assertEqual(first['target_hits'], 1)
            self.assertEqual(len((path/'premium_outcomes.jsonl').read_text().splitlines()), 1)
            self.assertEqual((path/'premium_outcomes.jsonl').stat().st_mode & 0o777, 0o600)

    def test_corrupt_outcomes_fail_without_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'premium_shadow.jsonl').write_text(json.dumps(event())+'\n')
            (path/'premium_outcomes.jsonl').write_text('broken')
            with self.assertRaises(ValueError):
                reconcile(directory, NOW+timedelta(minutes=8))
