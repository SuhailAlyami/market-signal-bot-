import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from hunter_runtime import HunterRuntime
from spx_cash_session import cash_active, cash_session
from spx_primary import run


def at(value):
    return datetime.fromisoformat(value)


class CashSessionTests(unittest.TestCase):
    def test_riyadh_open_changes_with_us_dst(self):
        for day, opening in [('2026-10-29', '16:30:00'), ('2026-11-02', '17:30:00')]:
            with self.subTest(day=day):
                info = cash_session(at(day+'T10:00:00+03:00'))
                self.assertFalse(info['is_open'])
                self.assertEqual(info['next_open_riyadh'], day+'T'+opening+'+03:00')
                self.assertTrue(cash_active(at(day+'T'+opening+'+03:00')))
        self.assertFalse(cash_active(at('2026-10-29T23:00:00+03:00')))

    def test_weekends_holidays_and_early_close(self):
        self.assertFalse(cash_active(at('2026-10-31T18:00:00+03:00')))
        self.assertFalse(cash_active(at('2026-11-26T18:00:00+03:00')))
        before = cash_session(at('2026-11-27T20:59:59+03:00'))
        self.assertTrue(before['is_open'])
        self.assertEqual(before['close_riyadh'], '2026-11-27T21:00:00+03:00')
        self.assertFalse(cash_active(at('2026-11-27T21:00:00+03:00')))
        with self.assertRaises(ValueError):
            cash_session(at('2026-10-29T10:00:00'))

    def test_runtime_closed_cash_never_fetches_despite_open_futures(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = HunterRuntime(Path(root)/'state.json', Path(root)/'journal.jsonl',
                                    symbols=('SPX',), market_active=cash_active)
            fetch = Mock(side_effect=AssertionError('must not fetch closed SPX'))
            with patch('hunter_runtime.futures_active', return_value=True):
                result = runtime.poll(at('2026-10-29T10:00:00+03:00'), fetch)
            fetch.assert_not_called()
            self.assertEqual(result['heartbeat']['status'], 'ok')
            self.assertEqual(result['heartbeat']['symbols']['SPX']['status'], 'closed')

    def test_monitor_waits_without_connecting_gateway_before_cash_open(self):
        now = at('2026-10-29T10:00:00+03:00')
        stop = Mock(); stop.is_set.side_effect = [False, True]
        with tempfile.TemporaryDirectory() as root:
            with patch('spx_primary.datetime') as clock, patch('spx_primary.connect_primary') as connect:
                clock.now.return_value = now
                run(root, Mock(), stop)
            connect.assert_not_called()
            report = json.loads((Path(root)/'spx/status.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'waiting_for_cash_session')
            self.assertEqual(report['cash_session']['next_open_riyadh'], '2026-10-29T16:30:00+03:00')
            self.assertNotIn('blocker', report)

    def test_calendar_failure_is_not_reported_as_waiting(self):
        stop = Mock(); stop.is_set.side_effect = [False, True]
        with tempfile.TemporaryDirectory() as root:
            with patch('spx_primary.cash_session', side_effect=RuntimeError('calendar unavailable')):
                run(root, Mock(), stop)
            report = json.loads((Path(root)/'spx/status.json').read_text(encoding='utf-8'))
            self.assertEqual(report['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
