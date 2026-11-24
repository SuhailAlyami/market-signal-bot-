import unittest
from datetime import date, timedelta

import numpy as np

from trend_24h_study import (
    build_configs,
    find_events,
    month_not_dominated,
    promotion_decision,
    session_bucket,
    simulate,
    split_60_20_20,
)


def _times(n, step_min=1):
    start = np.datetime64("2026-07-01T13:30")
    return start + np.arange(n) * np.timedelta64(step_min, "m")


class TrendStudyTests(unittest.TestCase):
    def test_split_is_the_last_fifth(self):
        days = [date(2025, 1, 1) + timedelta(days=i) for i in range(100)]
        parts = split_60_20_20(days)
        self.assertEqual(len(parts["test"]), 20)
        self.assertEqual(len(parts["validation"]), 20)
        self.assertLess(parts["validation"][-1], parts["test"][0])

    def test_smooth_rise_is_a_trend_and_a_dip_first_is_not(self):
        close = np.linspace(100, 101, 80)
        high = close + 0.01
        low = close - 0.01
        times = _times(80).astype("int64")
        events = find_events(high, low, close, times, 0.0075, 0.003, int(4 * 3600 * 1e9))
        self.assertTrue(events)
        self.assertEqual(events[0][1], 1)
        dipped = close.copy()
        dipped[1:4] = 99.5
        low_d = dipped - 0.01
        low_d[1:4] = 99.4
        high_d = dipped + 0.01
        none = find_events(high_d, low_d, dipped, times, 0.0075, 0.003, int(4 * 3600 * 1e9))
        self.assertFalse(any(start == 0 and side == 1 for start, side, _touch in none))

    def test_both_sides_of_the_cost_are_charged_on_a_stop(self):
        ts = _times(4)
        trades = simulate(
            ts, np.array([100.0, 100.0, 100.0, 100.0]),
            np.array([100.0, 100.2, 100.2, 100.2]),
            np.array([99.0, 90.0, 90.0, 90.0]),
            np.array([100.0, 99.0, 99.0, 99.0]),
            np.array([date(2026, 7, 1)] * 4, dtype=object),
            np.array([0]), np.array([1]), np.array([2.0]),
            {"init": 1.5, "trail": 3.0, "hours": 6, "be": 0}, 0.5,
        )
        # Stop is 1.5 * 2 = 3 points under the quoted open, then another 0.5 on the way out,
        # and the entry already paid 0.5.
        self.assertAlmostEqual(trades[0]["pnl"], -3.0 - 1.0, places=6)

    def test_one_month_cannot_carry_promotion(self):
        months = [
            {"total": 10.0}, {"total": 1.0}, {"total": 1.0}, {"total": -2.0},
        ]
        self.assertFalse(month_not_dominated(months))
        balanced = [{"total": 2.0}, {"total": 2.0}, {"total": 2.0}, {"total": 1.0}]
        self.assertTrue(month_not_dominated(balanced))
        self.assertFalse(promotion_decision(
            {"name": "x"}, {"expectancy_ci": [0.1, 0.2], "profit_factor": 1.4},
            {"survives": True}, {"survives": True}, months,
        )["promote"])

    def test_session_buckets_cover_the_overnight(self):
        self.assertEqual(session_bucket(19, 0), "asia")
        self.assertEqual(session_bucket(4, 0), "europe")
        self.assertEqual(session_bucket(8, 15), "us_pre")
        self.assertEqual(session_bucket(9, 30), "rth")
        self.assertEqual(session_bucket(16, 5), "after")

    def test_grid_is_the_predeclared_fifty(self):
        self.assertEqual(len(build_configs()), 50)


if __name__ == "__main__":
    unittest.main()
