import unittest
from datetime import timedelta

import numpy as np
import pandas as pd

from research_1m_lead import legacy_signals
from tune_legacy_thresholds import promote_legacy, select_legacy


def _bars(periods: int = 40) -> pd.DataFrame:
    start = pd.Timestamp("2026-10-20 13:30", tz="UTC")
    rows = []
    for step in range(periods * 5):
        price = 100.0
        if step >= 35 * 5:
            price = 100.25
        rows.append((start + timedelta(minutes=step), price))
    index = pd.DatetimeIndex([item[0] for item in rows])
    close = np.array([item[1] for item in rows])
    return pd.DataFrame({
        "Open": close, "High": close + 0.02, "Low": close - 0.02,
        "Close": close, "Volume": np.where(close > 100, 500.0, 100.0),
    }, index=index)


class LegacyTuneTests(unittest.TestCase):
    def test_lower_momentum_can_fire_when_the_default_does_not(self):
        frame = _bars()
        self.assertEqual(legacy_signals(frame), [])
        earlier = legacy_signals(frame, lookback=15, rvol_min=1.5, momentum_pct=0.15, min_distance_atr=0.05)
        self.assertTrue(earlier)
        self.assertEqual(earlier[0]["direction"], "BULLISH")

    def test_selection_stays_near_the_default_false_alarm_band(self):
        baseline = {"name": "default", "signals": 3, "forward_hit_rate": 0.6, "false_alarms_per_session": 0.25,
                    "recall_before_onset": 0.0, "median_lead_min": -4.0}
        noisy = {"name": "noisy", "signals": 40, "forward_hit_rate": 0.55, "false_alarms_per_session": 8.0,
                 "recall_before_onset": 0.5, "median_lead_min": 10.0}
        close = {"name": "close", "signals": 4, "forward_hit_rate": 0.55, "false_alarms_per_session": 0.5,
                 "recall_before_onset": 0.2, "median_lead_min": 2.0}
        choice = select_legacy([baseline, noisy, close], baseline)
        self.assertEqual(choice["selected"], "close")

    def test_overlapping_intervals_do_not_change_defaults(self):
        baseline = {
            "name": "lb30_rv2.0_m0.35_d0.10",
            "recall_before_onset_wilson95": [0.05, 0.30],
            "median_lead_bootstrap95": [-5, 8],
            "forward_hit_wilson95": [0.3, 0.7],
            "false_alarms_per_session": 1.0,
        }
        candidate = {
            "name": "lb15_rv1.5_m0.15_d0.05",
            "recall_before_onset_wilson95": [0.10, 0.40],
            "median_lead_bootstrap95": [-2, 12],
            "forward_hit_wilson95": [0.25, 0.6],
            "false_alarms_per_session": 1.2,
        }
        self.assertFalse(promote_legacy(candidate, baseline)["promote"])


if __name__ == "__main__":
    unittest.main()
