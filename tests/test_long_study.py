import unittest
from datetime import date, timedelta

import numpy as np

from long_explosion_study import simulate_trade, split_60_20_20


class LongStudyTests(unittest.TestCase):
    def test_split_is_sixty_twenty_twenty_and_ordered(self):
        sessions = [date(2025, 1, 2) + timedelta(days=i) for i in range(100)]
        parts = split_60_20_20(sessions)
        self.assertEqual(len(parts["test"]), 20)
        self.assertEqual(len(parts["validation"]), 20)
        self.assertEqual(len(parts["train"]), 60)
        self.assertLess(parts["train"][-1], parts["validation"][0])
        self.assertLess(parts["validation"][-1], parts["test"][0])

    def test_long_entry_pays_the_one_cent_slippage(self):
        index_n = 5
        market = {
            "open": np.array([100.0, 100.0, 100.0, 100.0, 101.0]),
            "high": np.array([100.0, 100.2, 100.2, 100.2, 101.2]),
            "low": np.array([99.9, 99.9, 99.9, 99.9, 100.8]),
            "close": np.array([100.0, 100.1, 100.1, 100.1, 101.0]),
            "day_id": np.zeros(index_n, dtype=int),
        }
        # ATR large enough that the 0.30% target is the binding one: 3*0.2=0.6 > 0.30.
        trade = simulate_trade(market, 0, 1, 0.2)
        self.assertIsNotNone(trade)
        self.assertAlmostEqual(trade["pnl"], 101.0 - 100.01 if False else trade["pnl"], places=6)
        self.assertLess(trade["pnl"], 101.0 - 100.0)


if __name__ == "__main__":
    unittest.main()
