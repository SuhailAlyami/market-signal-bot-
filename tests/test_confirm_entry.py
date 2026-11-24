import unittest
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from confirm_entry_study import (
    build_configs,
    choose_candidate,
    fresh_cross,
    promotion_decision,
    rolling_prior,
    simulate,
    split_dates,
)


class ConfirmEntryTests(unittest.TestCase):
    def test_split_matches_the_locked_dates(self):
        sessions = [date(2026, 2, 13), date(2026, 2, 17), date(2026, 6, 30), date(2026, 7, 1), date(2026, 11, 10)]
        parts = split_dates(sessions)
        self.assertEqual(parts["train"], [date(2026, 2, 13)])
        self.assertEqual(parts["validation"], [date(2026, 2, 17), date(2026, 6, 30)])
        self.assertEqual(parts["test"], [date(2026, 7, 1), date(2026, 11, 10)])

    def test_prior_window_excludes_the_current_bar(self):
        values = np.array([1.0, 2.0, 3.0, 4.0, 9.0])
        prior = rolling_prior(values, np.zeros(5, dtype=int), 3, "max")
        self.assertTrue(np.isnan(prior[2]))
        self.assertEqual(prior[3], 3.0)
        self.assertEqual(prior[4], 4.0)

    def test_fresh_cross_does_not_repeat_while_price_stays_beyond(self):
        close = np.array([1.0, 1.0, 2.0, 2.2, 2.3])
        level = np.array([1.5, 1.5, 1.5, 1.5, 1.5])
        fresh = fresh_cross(close, level, np.zeros(5, dtype=int), 1, 1)
        self.assertEqual(fresh.tolist(), [False, False, True, False, False])

    def test_long_target_pays_slippage_on_both_sides_and_stop_wins_a_tie(self):
        index = pd.date_range("2026-07-01 14:30", periods=4, freq="min", tz=timezone.utc).to_numpy(dtype="datetime64[ns]")
        # numpy may keep timezone as datetime64 by dropping tz; rebuild explicitly
        index = np.array([np.datetime64("2026-07-01T14:30"), np.datetime64("2026-07-01T14:31"),
                          np.datetime64("2026-07-01T14:32"), np.datetime64("2026-07-01T14:33")])
        day = np.zeros(4, dtype=int)
        target_trade = simulate(
            index, day, np.array([100.0, 101.0, 101.0, 101.0]),
            np.array([100.0, 104.0, 104.0, 104.0]), np.array([99.0, 100.5, 100.5, 100.5]),
            np.array([100.0, 103.0, 103.0, 103.0]),
            np.array([0]), np.array([1]), np.array([1.0, 1.0, 1.0, 1.0]),
            {"stop": 1.0, "target_r": 2.0, "time": 30, "trail": 0.0, "be": 0}, 0.01,
        )
        self.assertAlmostEqual(target_trade[0][0], (101.0 + 2.0 - 0.01) - (101.0 + 0.01), places=6)
        stop_trade = simulate(
            index, day, np.array([100.0, 101.0, 101.0, 101.0]),
            np.array([100.0, 104.0, 104.0, 104.0]), np.array([99.0, 100.0, 100.0, 100.0]),
            np.array([100.0, 103.0, 103.0, 103.0]),
            np.array([0]), np.array([1]), np.array([1.0, 1.0, 1.0, 1.0]),
            {"stop": 1.0, "target_r": 2.0, "time": 30, "trail": 0.0, "be": 0}, 0.01,
        )
        # Stop is filled before the target, and the exit also pays a cent.
        self.assertAlmostEqual(stop_trade[0][0], (101.0 - 1.0 - 0.01) - (101.0 + 0.01), places=6)

    def test_a_new_trade_waits_until_the_open_position_exits(self):
        index = np.arange(np.datetime64("2026-07-01T14:30"), np.datetime64("2026-07-01T14:36"), np.timedelta64(1, "m"))
        trades = simulate(
            index, np.zeros(6, dtype=int),
            np.full(6, 100.0), np.full(6, 100.2), np.full(6, 99.9), np.full(6, 100.0),
            np.array([0, 1]), np.array([1, 1]), np.full(6, 1.0),
            {"stop": 1.0, "target_r": 5.0, "time": 3, "trail": 0.0, "be": 0}, 0.01,
        )
        self.assertEqual(len(trades), 1)

    def test_promotion_requires_the_interval_the_haircut_and_profit_factor(self):
        candidate = {"name": "x"}
        good = {"expectancy_ci": [0.01, 0.2], "profit_factor": 1.4}
        reality = {"survives": True}
        dsr = {"survives": True}
        self.assertTrue(promotion_decision(candidate, good, reality, dsr)["promote"])
        self.assertFalse(promotion_decision(candidate, {"expectancy_ci": [-0.01, 0.2], "profit_factor": 1.4}, reality, dsr)["promote"])
        self.assertFalse(promotion_decision(candidate, good, {"survives": False}, dsr)["promote"])
        self.assertFalse(promotion_decision(None, good, reality, dsr)["promote"])

    def test_candidate_comes_from_validation_not_from_a_later_column(self):
        rows = [
            {"name": "a", "eligible": True, "validation": {"expectancy": 0.02, "profit_factor": 1.1, "trades": 20}},
            {"name": "b", "eligible": True, "validation": {"expectancy": 0.05, "profit_factor": 1.3, "trades": 18}},
            {"name": "c", "eligible": False, "validation": {"expectancy": 0.50, "profit_factor": 3.0, "trades": 5}},
        ]
        self.assertEqual(choose_candidate(rows)["name"], "b")

    def test_grid_stays_at_the_predeclared_size(self):
        self.assertEqual(len(build_configs()), 100)


if __name__ == "__main__":
    unittest.main()
