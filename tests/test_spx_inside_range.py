import json
from pathlib import Path
import unittest

import pandas as pd

from spx_inside_range import (CLOSE_LOCATION, VERSION, directions, features, gap_minutes,
                              lifecycle, signal_schedule, strict_early_slots)


def frame(count=80):
    index = pd.date_range('2026-10-22T14:00Z', periods=count, freq='min')
    bars = pd.DataFrame({'Open': [100.] * count, 'High': [100.2] * count,
                         'Low': [99.8] * count, 'Close': [100.] * count}, index=index)
    bars.attrs.update(symbol='SPX', security_type='IND')
    return bars


def quiet_up(bars, index):
    bars.iloc[index] = [100.0, 100.15, 99.9, 100.12]


class InsideRangeTests(unittest.TestCase):
    def test_constants_are_the_published_cut_not_a_new_search(self):
        self.assertEqual(VERSION, 'spx-inside-range-v1')
        self.assertEqual(CLOSE_LOCATION, 0.60)

    def test_local_break_is_not_readiness_and_quiet_inside_bar_is(self):
        bars = frame()
        quiet_up(bars, 40)
        self.assertEqual(directions(features(bars), 'inside_range_pressure').iloc[40], 1)
        bars.iloc[40] = [100.05, 100.4, 100.0, 100.3]
        self.assertEqual(directions(features(bars), 'inside_range_pressure').iloc[40], 0)
        self.assertEqual(directions(features(bars), 'original_candidate').iloc[40], 1)

    def test_future_suffix_and_receipt_clock_do_not_move_the_decision(self):
        bars = frame()
        quiet_up(bars, 40)
        before = features(bars)
        expected = signal_schedule(before, 'inside_range_pressure')
        changed = bars.copy()
        changed.iloc[50:] += 1000
        changed.attrs.update(symbol='SPX', security_type='IND')
        poisoned = [row for row in signal_schedule(features(changed), 'inside_range_pressure')
                    if row['index'] < 50]
        self.assertEqual(poisoned, [row for row in expected if row['index'] < 50])
        prefix = signal_schedule(features(bars.iloc[:50]), 'inside_range_pressure')
        self.assertEqual(prefix, [row for row in expected if row['index'] < 50])
        for row in expected:
            self.assertEqual(row['detected_at'], (bars.index[row['index']] + pd.Timedelta(minutes=1)).isoformat())
            self.assertFalse(row['notify_eligible'])

    def test_confirmation_cancel_and_exit_are_separate_states(self):
        bars = frame(count=60)
        quiet_up(bars, 40)
        bars.iloc[42] = [100.05, 100.4, 100.0, 100.3]
        states = [row['state'] for row in lifecycle(features(bars))]
        self.assertEqual(states[:2], ['READINESS', 'CONFIRMATION'])
        flat = frame(count=50)
        quiet_up(flat, 40)
        cancelled = lifecycle(features(flat))
        self.assertEqual([row['state'] for row in cancelled], ['READINESS', 'CANCEL'])
        self.assertEqual(cancelled[1]['reason'], 'confirm_window_elapsed')
        exited = frame(count=60)
        quiet_up(exited, 40)
        exited.iloc[41] = [100.05, 100.4, 100.0, 100.3]
        exited.iloc[44] = [100.2, 100.25, 99.7, 99.75]
        trail = lifecycle(features(exited))
        self.assertEqual([row['state'] for row in trail[:3]], ['READINESS', 'CONFIRMATION', 'EXIT'])

    def test_zero_gap_has_no_legal_strict_early_slot_at_any_finer_bar(self):
        index = pd.date_range('2026-10-22T15:00Z', periods=5, freq='min')
        bars = pd.DataFrame({'Open': 1, 'High': 1, 'Low': 1, 'Close': 1}, index=index)
        event = dict(anchor_index=1, target_index=4, anchor_time=index[1].isoformat(),
                     onset_time=(index[1] + pd.Timedelta(minutes=1)).isoformat())
        self.assertEqual(gap_minutes(event), 0)
        self.assertEqual(strict_early_slots(event, bars), [])
        onset = pd.Timestamp(event['onset_time'])
        anchor_decision = pd.Timestamp(event['anchor_time']) + pd.Timedelta(minutes=1)
        self.assertFalse(onset > anchor_decision)

    def test_published_oct22_attribution_still_has_nine_zero_gaps(self):
        path = Path(__file__).resolve().parents[1] / 'artifacts/spx_only_development/miss_attribution.json'
        payload = json.loads(path.read_text())
        zero = 0
        for event in payload['event_attribution']:
            self.assertAlmostEqual(gap_minutes(event), event['minutes_from_anchor_decision_to_onset'])
            if gap_minutes(event) <= 0:
                zero += 1
        self.assertEqual(zero, 9)
        self.assertEqual(len(payload['event_attribution']), 16)
        causes = {row['event_id']: row['diagnostic_cause'] for row in payload['event_attribution']}
        self.assertEqual(causes[0], 'first_price_candidate_at_or_after_onset')
        self.assertEqual(causes[4], 'no_matching_price_candidate_before_target')
        self.assertGreater(gap_minutes(payload['event_attribution'][0]), 0)
        self.assertEqual(gap_minutes(payload['event_attribution'][4]), 0)

    def test_session_restart_does_not_import_the_previous_day(self):
        first, second = frame(), frame(20)
        second.index += pd.Timedelta(days=1)
        both = pd.concat([first, second])
        both.attrs.update(symbol='SPX', security_type='IND')
        frame_both = features(both)
        self.assertTrue(directions(frame_both, 'inside_range_pressure').iloc[-20:].eq(0).all())

    def test_last_body_baseline_is_not_the_inside_range_rule(self):
        bars = frame()
        bars.iloc[40] = [100.1, 100.15, 99.95, 100.0]
        side = directions(features(bars), 'last_body')
        self.assertEqual(int(side.iloc[40]), -1)
        self.assertEqual(int(directions(features(bars), 'inside_range_pressure').iloc[40]), 0)
        self.assertEqual(signal_schedule(features(bars), 'no_signal'), [])


if __name__ == '__main__':
    unittest.main()
