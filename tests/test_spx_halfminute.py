from pathlib import Path
import unittest
from unittest.mock import patch

import pandas as pd

from research_spx_halfminute import MODELS, load_halves, midpoint_features, minute_pairs, signals


class HalfMinuteTests(unittest.TestCase):
    def fixture(self):
        path = Path(__file__).resolve().parents[1] / 'artifacts/spx_halfminute_20261023/raw.json'
        native, _, _, _ = load_halves(path)
        return native.loc[native.index.strftime('%Y-%m-%d') == '2026-10-22'].copy()

    def test_missing_native_half_is_never_filled(self):
        native = self.fixture()
        with self.assertRaisesRegex(ValueError, 'missing_native_half'):
            minute_pairs(native.drop(native.index[100]))

    def test_future_second_half_and_later_prices_cannot_change_midpoint_decision(self):
        native = self.fixture()
        minutes = minute_pairs(native)
        _, original = midpoint_features(minutes, native)
        minute = minutes.index[120]
        deadline = minute + pd.Timedelta(seconds=30)
        changed = native.copy()
        changed.loc[changed.index >= deadline] += 1000
        new_minutes = minute_pairs(changed)
        _, actual = midpoint_features(new_minutes, changed)
        for key in ('close', 'body', 'position', 'move3', 'move15', 'ema5', 'ema15',
                    'slope5', 'atr', 'compression', 'prior_high20', 'prior_low20', 'valid'):
            pd.testing.assert_series_equal(original[key].loc[:minute], actual[key].loc[:minute])
        for model in MODELS:
            old = [s for s in signals(original, model, 'midpoint', native)
                   if pd.Timestamp(s['detected_at']) <= deadline]
            new = [s for s in signals(actual, model, 'midpoint', changed)
                   if pd.Timestamp(s['detected_at']) <= deadline]
            self.assertEqual(old, new, model)

    def test_clocks_map_to_known_native_half_close(self):
        native = self.fixture()
        minutes = minute_pairs(native)
        base, mid = midpoint_features(minutes, native)
        i = 100
        side = pd.Series(0, index=minutes.index)
        side.iloc[i] = 1
        with patch('research_spx_halfminute.candidate_directions', return_value=side):
            half = signals(mid, 'pullback_release', 'midpoint', native)[0]
            full = signals(base, 'pullback_release', 'minute_close', native)[0]
        self.assertEqual(half['index'], i * 2)
        self.assertEqual(full['index'], i * 2 + 1)
        self.assertEqual(pd.Timestamp(half['detected_at']), native.index[half['index']] + pd.Timedelta(seconds=30))
        self.assertEqual(pd.Timestamp(full['detected_at']), native.index[full['index']] + pd.Timedelta(seconds=30))

    def test_midpoint_requires_previous_completed_context(self):
        native = self.fixture()
        base, mid = midpoint_features(minute_pairs(native), native)
        self.assertFalse(base.valid.iloc[:30].any())
        self.assertTrue(base.valid.iloc[30])
        self.assertFalse(mid.valid.iloc[:31].any())
        self.assertTrue(mid.valid.iloc[31])


if __name__ == '__main__':
    unittest.main()
