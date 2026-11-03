import unittest
from datetime import datetime, timezone, timedelta
import pandas as pd
import exchange_calendars as xc

from close_policy import (
    adopt_filter, closed_starts, continuation, is_closed_at_capture, parse_time, wilson,
)
from watcher import evaluate, fresh_state, riyadh


def bar(start, slot):
    return {'start': start, 'slot': slot}


class PolicyTests(unittest.TestCase):
    def test_processing_delay_does_not_complete_a_forming_snapshot(self):
        start = '2026-11-03T15:00:00Z'
        captured = '2026-11-03T15:03:00Z'
        processed = '2026-11-03T15:06:00Z'
        self.assertFalse(is_closed_at_capture(start, captured))
        self.assertTrue(parse_time(processed) >= parse_time(start) + timedelta(minutes=5))
        self.assertEqual(closed_starts([start], captured), [])
        self.assertEqual(closed_starts([start], '2026-11-03T15:05:00Z'), [start])

    def test_capture_time_required(self):
        with self.assertRaises(ValueError):
            parse_time(None)
        with self.assertRaises(ValueError):
            parse_time('2026-11-03T15:00:00')

    def test_continuation_is_not_the_rejected_channel_rule(self):
        self.assertTrue(continuation(1, 0.2))
        self.assertFalse(continuation(-1, 0.2))
        self.assertFalse(continuation(1, 0.0))
        self.assertFalse(continuation(1, float('nan')))

    def test_adoption_rejects_deleting_correct_signals_and_small_samples(self):
        wiped = adopt_filter(10, 12, 2, 3)
        self.assertFalse(wiped['shadow_research_candidate'])
        self.assertFalse(wiped['seventy_percent_claim_supported'])
        tiny = adopt_filter(6, 6, 1, 1)
        self.assertFalse(tiny['shadow_research_candidate'])
        kept = adopt_filter(10, 12, 10, 10)
        self.assertTrue(kept['shadow_research_candidate'])
        self.assertFalse(kept['trading_ready'])
        self.assertFalse(kept['frozen_weights_changed'])

    def test_wilson_interval_contains_point_estimate(self):
        lo, hi = wilson(10, 12)
        self.assertLess(lo, 10 / 12)
        self.assertGreater(hi, 10 / 12)
        self.assertLess(lo, 0.70)

    def test_missing_es_does_not_burn_bar_or_duplicate(self):
        state = fresh_state('abc')
        spx = [bar('2026-11-03T15:00:00Z', 10)]
        qualify = lambda spx_bar, es_bar: {'slot': spx_bar['slot'], 'side': 1, 'bar_start': spx_bar['start']}
        state, alerts = evaluate(spx, [], '2026-11-03T15:05:00Z', '2026-11-03T15:05:00Z', state, qualify)
        self.assertEqual(alerts, [])
        self.assertEqual(state['resolved_bar_starts'], [])
        es = [bar('2026-11-03T15:00:00Z', 10)]
        state, alerts = evaluate(spx, es, '2026-11-03T15:05:00Z', '2026-11-03T15:05:00Z', state, qualify)
        self.assertEqual(len(alerts), 1)
        state, again = evaluate(spx, es, '2026-11-03T15:05:00Z', '2026-11-03T15:05:00Z', state, qualify)
        self.assertEqual(again, [])

    def test_low_score_does_not_consume_cooldown(self):
        state = fresh_state('abc')
        bars = [bar('2026-11-03T15:00:00Z', 10), bar('2026-11-03T15:05:00Z', 11)]

        def qualify(spx_bar, es_bar):
            if spx_bar['slot'] == 10:
                return None
            return {'slot': spx_bar['slot'], 'side': -1, 'bar_start': spx_bar['start']}

        state, alerts = evaluate(bars, bars, '2026-11-03T15:10:00Z', '2026-11-03T15:10:00Z', state, qualify)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['slot'], 11)

    def test_cooldown_and_shadow_do_not_drop_the_frozen_comparison_row(self):
        state = fresh_state('abc')
        bars = [bar('2026-11-03T15:00:00Z', 10), bar('2026-11-03T15:10:00Z', 12)]

        def qualify(spx_bar, es_bar):
            return {'slot': spx_bar['slot'], 'side': 1, 'bar_start': spx_bar['start']}

        state, alerts = evaluate(bars, bars, '2026-11-03T15:15:00Z', '2026-11-03T15:15:00Z', state, qualify, shadow=lambda s: True)
        self.assertEqual(len(alerts), 1)
        self.assertTrue(alerts[0]['shadow_veto'])
        self.assertEqual([row.get('suppressed') for row in state['signals']], [None, 'COOLDOWN'])

    def test_riyadh_and_nyse_early_close_and_dst(self):
        self.assertEqual(riyadh('2026-11-03T15:05:00Z'), '2026-11-03 18:05:00+03:00')
        cal = xc.get_calendar('XNYS', start='2026-01-01', end='2026-12-31')
        early = cal.schedule.loc['2026-11-27']
        self.assertEqual(pd.Timestamp(early.close), pd.Timestamp('2026-11-27 18:00', tz='UTC'))
        self.assertEqual(str(pd.Timestamp(early.close).tz_convert('Asia/Riyadh')), '2026-11-27 21:00:00+03:00')
        july = cal.schedule.loc['2026-07-06']
        november = cal.schedule.loc['2026-11-03']
        self.assertEqual(pd.Timestamp(july.open), pd.Timestamp('2026-07-06 13:30', tz='UTC'))
        self.assertEqual(pd.Timestamp(november.open), pd.Timestamp('2026-11-03 14:30', tz='UTC'))
        self.assertFalse(bool(cal.is_session('2026-11-26')))
        self.assertTrue(bool(cal.is_session('2026-11-27')))


if __name__ == '__main__':
    unittest.main()
