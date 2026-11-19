"""Offline tests: move-from-open lines and TradingAgents shadow scoring (no network)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_range as D  # noqa: E402
import evaluate_range as E  # noqa: E402


def spy(*closes):
    days = ['2026-11-12', '2026-11-13', '2026-11-16', '2026-11-17', '2026-11-18'][:len(closes)]
    return {d: (c, c, c, c) for d, c in zip(days, closes)}


def records(tmp, **sig):
    for d, s in sig.items():
        Path(tmp, f'{d}.json').write_text(json.dumps({'session': d.replace('_', '-'), 'signal': s}))
    return tmp


class MoveLinesTests(unittest.TestCase):
    def test_points_scale_with_expected_move_and_no_direction_claim(self):
        text = '\n'.join(D.move_lines(92.0))
        self.assertIn('23 نقطة في اتجاه واحد على الأقل: 96%', text)
        self.assertIn('46 نقطة في اتجاه واحد على الأقل: 69%', text)
        self.assertIn('القمة ≥ الافتتاح +9: 85%', text)
        self.assertIn('الاتجاه غير معروف', text)


class DailyCallTests(unittest.TestCase):
    def test_levels_from_previous_close(self):
        lv = D.call_levels(7561.67, 92.0)
        self.assertAlmostEqual(lv['high'], 7561.67+0.174*92, places=6)
        self.assertAlmostEqual(lv['low'], 7561.67-0.11*92, places=6)
        self.assertEqual((round(lv['min_low']), round(lv['max_high'])), (7470, 7654))

    def test_evaluation_flags_for_16_nov(self):
        spx = {'2026-11-13': (7500, 7621.78, 7499.40, 7561.67), '2026-11-16': (7513.98, 7515.60, 7400.15, 7416.59)}
        vix = {'2026-11-13': (0, 0, 0, 19.3), '2026-11-16': (0, 0, 0, 22.0)}
        e = E.evaluate(spx, vix, '2026-11-16')
        self.assertFalse(e['up']); self.assertFalse(e['hit_high']); self.assertTrue(e['hit_low']); self.assertFalse(e['in1'])


class GapCallTests(unittest.TestCase):
    def test_direction_buckets(self):
        self.assertEqual(D.gap_direction(-0.6)[0:3:2], ('down', 90))
        self.assertEqual(D.gap_direction(-0.3)[0:3:2], ('down', 74))
        self.assertEqual(D.gap_direction(0.0)[0], 'flat')
        self.assertEqual(D.gap_direction(0.3)[0:3:2], ('up', 76))
        self.assertEqual(D.gap_direction(0.7)[0:3:2], ('up', 89))

    def test_levels_anchor_on_implied_open(self):
        c = D.gap_call(7416.59, 107.0, -0.0024)
        a = 7416.59*(1-0.0024)
        self.assertAlmostEqual(c['anchor'], a, places=6)
        self.assertAlmostEqual(c['levels'][0]['high'], a+10.7, places=6)
        self.assertAlmostEqual(c['levels'][1]['low'], a-26.75, places=6)
        self.assertEqual(c['direction'], 'down')

    def test_stale_or_missing_futures_fall_back(self):
        from datetime import date, datetime, timezone
        from unittest import mock
        body = json.dumps({'chart': {'result': [{'timestamp': [1794853800], 'indicators': {'quote': [{'close': [7400.0]}]}}]}}).encode()
        class R:
            def read(self): return body
        with mock.patch('urllib.request.urlopen', return_value=R()):
            self.assertIsNone(D.es_move(date(2026, 11, 17), datetime(2026, 11, 17, 13, 41, tzinfo=timezone.utc)))

    def test_stored_call_is_scored_and_summarised(self):
        call = {'session': '2026-11-17', 'prev_close': 7416.59, 'direction': 'down', 'conf': 60, 'method': 'gap',
                'levels': [{'k': .1, 'high': 7410, 'low': 7388, 'p_high': 85, 'p_low': 80},
                           {'k': .25, 'high': 7426, 'low': 7372, 'p_high': 63, 'p_low': 60}], 'range': [7310, 7524]}
        with tempfile.TemporaryDirectory() as t:
            Path(t, '2026-11-17.json').write_text(json.dumps(call))
            spx = {'2026-11-16': (0, 0, 0, 7416.59), '2026-11-17': (7400, 7420, 7380, 7390)}
            text = '\n'.join(E.call_lines(t, spx, '2026-11-17'))
        self.assertIn('الاتجاه هابط (60%): ✅', text)
        self.assertIn('القمة ≥ 7,410 (85%): ✅ | القاع ≤ 7,388 (80%): ✅', text)
        self.assertIn('القمة ≥ 7,426 (63%): ❌ | القاع ≤ 7,372 (60%): ❌', text)
        self.assertIn('السجل (1 جلسة): الاتجاه 1/1', text)


class YahooRetryTests(unittest.TestCase):
    def test_retries_across_hosts_then_succeeds(self):
        import urllib.error
        from unittest import mock
        ok = json.dumps({'chart': {'result': [{'x': 1}]}}).encode()
        class R:
            def read(self): return ok
        seen = []
        def fake(req, timeout):
            seen.append(req.full_url.split('/')[2])
            if len(seen) < 3:
                raise urllib.error.HTTPError(req.full_url, 502, 'Bad Gateway', {}, None)
            return R()
        with mock.patch('urllib.request.urlopen', side_effect=fake):
            self.assertEqual(D.yahoo_chart('^GSPC', 'interval=1d', sleep=lambda s: None), {'x': 1})
        self.assertEqual(seen, ['query1.finance.yahoo.com', 'query2.finance.yahoo.com', 'query1.finance.yahoo.com'])

    def test_gives_up_with_data_unavailable(self):
        from unittest import mock
        with mock.patch('urllib.request.urlopen', side_effect=TimeoutError('read timed out')):
            with self.assertRaises(D.DataUnavailable):
                D.yahoo_chart('^GSPC', 'interval=1d', tries=3, sleep=lambda s: None)


class TelegramRetryTests(unittest.TestCase):
    def setUp(self):
        import os
        self.env = mock_env = {'TELEGRAM_BOT_TOKEN': 't', 'TELEGRAM_CHAT_ID': 'c'}
        self._old = {k: os.environ.get(k) for k in mock_env}
        os.environ.update(mock_env)

    def tearDown(self):
        import os
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_timeout_then_success(self):
        from unittest import mock
        class R:
            def read(self): return b'{"ok": true}'
        calls = []
        def fake(url, data, timeout):
            calls.append(1)
            if len(calls) < 2:
                raise TimeoutError('The read operation timed out')
            return R()
        with mock.patch('urllib.request.urlopen', side_effect=fake):
            self.assertTrue(D.send('x', sleep=lambda s: None))
        self.assertEqual(len(calls), 2)

    def test_client_error_not_retried_and_outage_gives_up(self):
        import urllib.error
        from unittest import mock
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('u', 400, 'Bad Request', {}, None)) as m:
            self.assertFalse(D.send('x', sleep=lambda s: None))
            self.assertEqual(m.call_count, 1)
        with mock.patch('urllib.request.urlopen', side_effect=TimeoutError('t')) as m:
            self.assertFalse(D.send('x', tries=3, sleep=lambda s: None))
            self.assertEqual(m.call_count, 3)


class ShadowScoringTests(unittest.TestCase):
    def test_no_records_dir_gives_nothing(self):
        self.assertEqual(E.shadow_lines(None, spy(100, 101), '2026-11-13'), [])
        self.assertEqual(E.shadow_lines('/nonexistent', spy(100, 101), '2026-11-13'), [])

    def test_hold_is_no_position_and_baseline_is_always_long(self):
        with tempfile.TemporaryDirectory() as t:
            out = E.shadow_lines(records(t, **{'2026_11_16': 'Hold'}), spy(100, 100, 98), '2026-11-16')
        text = '\n'.join(out)
        self.assertIn('بلا مركز', text)
        self.assertIn('-2.00%', text)          # SPY move and always-long baseline
        self.assertIn('قرارات اتجاه 0، صحيحة 0', text)
        self.assertIn('اتباعه +0.00%', text)

    def test_direction_hits_and_cumulative_pnl(self):
        with tempfile.TemporaryDirectory() as t:
            records(t, **{'2026_11_16': 'Sell', '2026_11_17': 'Buy', '2026_11_18': 'Buy'})
            out = E.shadow_lines(t, spy(100, 100, 98, 99, 99.5), '2026-11-17')   # 11-18 is after `day`: excluded
        text = '\n'.join(out)
        self.assertIn('✅ صحيح', text)          # Buy on 11-17, SPY +1.02%
        self.assertIn('التراكمي (2 جلسة)', text)
        self.assertIn('قرارات اتجاه 2، صحيحة 2', text)

    def test_wrong_call_marked(self):
        with tempfile.TemporaryDirectory() as t:
            out = E.shadow_lines(records(t, **{'2026_11_16': 'Buy'}), spy(100, 100, 98), '2026-11-16')
        self.assertIn('❌ خطأ', '\n'.join(out))


if __name__ == '__main__':
    unittest.main()
