import unittest

import numpy as np
import pandas as pd

from research_spx_lead_v2 import MODELS, directions, features, schedule


def frame(count=80):
    index = pd.date_range('2026-10-22T13:30Z', periods=count, freq='min')
    close = 7000 + np.arange(count) * .2
    bars = pd.DataFrame(dict(Open=close-.2, High=close+.5, Low=close-2, Close=close), index=index)
    bars.attrs.update(symbol='SPX', security_type='IND')
    return bars


class LeadV2Tests(unittest.TestCase):
    def test_future_changes_and_prefix_do_not_change_prior_signals(self):
        bars = frame()
        full = features(bars)
        prefix = features(bars.iloc[:50])
        changed = bars.copy()
        changed.iloc[50:] += 1000
        poisoned = features(changed)
        for model in MODELS:
            expected = [s for s in schedule(full, model) if s['index'] < 50]
            self.assertEqual(schedule(prefix, model), expected)
            self.assertEqual([s for s in schedule(poisoned, model) if s['index'] < 50], expected)

    def test_ols_slope_and_price_scale_invariance(self):
        bars = frame()
        f = features(bars)
        for n in (3, 5, 10):
            self.assertAlmostEqual(f[f'slope{n}'].iloc[-1], .2)
        scaled = features(bars * 10)
        for model in MODELS:
            self.assertEqual(schedule(f, model), schedule(scaled, model))

    def test_missing_minute_blocks_signals_until_contiguous_history_recovers(self):
        bars = frame().drop(frame().index[20])
        f = features(bars)
        self.assertFalse(f.valid.iloc[40])
        self.assertTrue(f.valid.iloc[-1])
        for model in MODELS:
            self.assertEqual(directions(f, model).iloc[40], 0)

    def test_prelevel_pressure_is_inside_level_and_stops_after_break(self):
        bars = frame()
        self.assertEqual(directions(features(bars), 'prelevel_pressure').iloc[-1], 1)
        bars.iloc[-1, bars.columns.get_loc('Close')] = bars.High.iloc[-2] + .1
        self.assertNotEqual(directions(features(bars), 'prelevel_pressure').iloc[-1], 1)

    def test_session_warmup_restarts_and_does_not_import_prior_day_slope(self):
        first, second = frame(), frame(15)
        second.index += pd.Timedelta(days=1)
        second += 1000
        both = pd.concat([first, second])
        both.attrs.update(symbol='SPX', security_type='IND')
        f = features(both)
        self.assertFalse(f.valid.iloc[-15:].any())
        self.assertTrue(f.slope10.iloc[-15:-6].isna().all())
        for model in MODELS:
            self.assertTrue(directions(f, model).iloc[-15:].eq(0).all())


if __name__ == '__main__':
    unittest.main()
