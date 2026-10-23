import unittest
from unittest.mock import patch
import pandas as pd

from spx_inside_range import lifecycle
from spx_inside_range_safe import lifecycle_safe


def fixture():
    index = pd.date_range('2026-10-22T14:00Z', periods=16, freq='min')
    return pd.DataFrame(dict(valid=True, close=100., low=99., high=101.,
                             original_direction=0), index=index)


def run(frame, sides, function=lifecycle_safe):
    # Fixed feature-level scenario isolates state transitions from the detector.
    series = pd.Series(sides, index=frame.index)
    module = 'spx_inside_range' if function is lifecycle else 'spx_inside_range_safe'
    with patch(module+'.directions', return_value=series):
        return function(frame)


class SafeLifecycleTests(unittest.TestCase):
    def test_gap_or_session_change_never_confirms_old_readiness(self):
        for shift in (pd.Timedelta(minutes=2), pd.Timedelta(days=1)):
            with self.subTest(shift=shift):
                frame = fixture().iloc[:3].copy()
                frame.index = pd.DatetimeIndex([frame.index[0],frame.index[1]+shift,frame.index[2]+shift])
                frame.iloc[1, frame.columns.get_loc('original_direction')] = 1
                original = run(frame, [1,0,0], lifecycle)
                self.assertEqual(original[1]['state'], 'CONFIRMATION')
                safe = run(frame, [1,0,0])
                self.assertEqual([x['state'] for x in safe], ['READINESS','CANCEL'])
                self.assertEqual(safe[1]['reason'], 'context_discontinuity')
                self.assertEqual(safe[1]['detected_at'], (frame.index[1]+pd.Timedelta(minutes=1)).isoformat())

    def test_invalid_context_and_invalidation_preempt_confirmation(self):
        for invalid_context in (True, False):
            frame = fixture().iloc[:3].copy()
            frame.loc[frame.index[1], 'original_direction'] = 1
            if invalid_context:
                frame.loc[frame.index[1], 'valid'] = False
            else:
                frame.loc[frame.index[1], 'close'] = 98.
            states = run(frame, [1,0,0])
            self.assertEqual(states[1]['state'], 'CANCEL')
            self.assertNotIn('CONFIRMATION', [x['state'] for x in states])

    def test_three_minute_boundary_confirm_or_expire_without_rearm(self):
        for confirm in (True, False):
            frame = fixture().iloc[:5].copy()
            if confirm:
                frame.loc[frame.index[3], 'original_direction'] = 1
            states = run(frame, [1,0,0,1,0])
            self.assertEqual([x['state'] for x in states],
                             ['READINESS', 'CONFIRMATION' if confirm else 'CANCEL'])
            self.assertEqual(states[1]['index'], 3)

    def test_confirmed_exit_and_future_prefix_stability(self):
        frame = fixture()
        frame.loc[frame.index[1], 'original_direction'] = 1
        sides = [1]+[0]*15
        all_events = run(frame, sides)
        self.assertEqual([x['state'] for x in all_events], ['READINESS','CONFIRMATION','EXIT'])
        self.assertEqual(all_events[-1]['index'], 11)
        prefix = run(frame.iloc[:6], sides[:6])
        self.assertEqual(prefix, [x for x in all_events if x['index'] < 6])
        changed = frame.copy(); changed.iloc[6:, changed.columns.get_loc('close')] = 98.
        self.assertEqual(prefix, [x for x in run(changed, sides) if x['index'] < 6])
        changed = frame.copy(); changed.loc[changed.index[2], 'valid'] = False
        self.assertEqual(run(changed, sides)[2]['reason'], 'context_discontinuity')


if __name__ == '__main__':
    unittest.main()
