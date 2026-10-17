import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pandas as pd

from backtest_explosion import study


class BacktestTests(unittest.TestCase):
    def setUp(self):
        start = datetime(2026, 10, 16, 16, 0, tzinfo=timezone.utc)
        index = pd.date_range(start, periods=60, freq="5min")
        self.bars = pd.DataFrame({
            "Open": [100.] * 60, "High": [100.2] * 60,
            "Low": [99.8] * 60, "Close": [100.] * 60,
            "Volume": [100.] * 60,
        }, index=index)

    def test_future_bars_not_visible_to_signal(self):
        seen_lengths = []
        def fake_assess(symbol, prefix, now):
            seen_lengths.append(len(prefix))
            self.assertEqual(prefix.index[-1] + timedelta(minutes=5, seconds=30), pd.Timestamp(now))
            return None
        with patch("backtest_explosion.market_session_open", return_value=True):
            with patch("backtest_explosion.assess_bars", side_effect=fake_assess):
                result = study("SPY", self.bars, horizon=6)
        self.assertGreater(len(seen_lengths), 0)
        self.assertEqual(seen_lengths[0], 33)
        self.assertEqual(max(seen_lengths), len(self.bars) - 6)
        self.assertIsNone(result["positive_direction_rate"])

    def test_rejects_naive_index(self):
        bad = self.bars.copy()
        bad.index = bad.index.tz_localize(None)
        with self.assertRaises(ValueError):
            study("SPY", bad)


if __name__ == "__main__":
    unittest.main()
