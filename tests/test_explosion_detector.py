import unittest
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from explosion_detector import assess_bars, format_alert


class ExplosionDetectorTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 16, 19, 5, tzinfo=timezone.utc)
        start = self.now - timedelta(minutes=5 * 41 + 2)
        index = pd.date_range(start, periods=42, freq="5min", tz="UTC")
        self.bars = pd.DataFrame(
            {"Open": [100.] * 42, "High": [100.2] * 42,
             "Low": [99.8] * 42, "Close": [100.] * 42, "Volume": [100.] * 42},
            index=index,
        )

    def test_strong_breakout_on_completed_bar(self):
        self.bars.iloc[-2, self.bars.columns.get_loc("Close")] = 103.
        self.bars.iloc[-2, self.bars.columns.get_loc("High")] = 103.2
        self.bars.iloc[-2, self.bars.columns.get_loc("Volume")] = 500.
        result = assess_bars("SPY", self.bars, self.now)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "BULLISH")
        self.assertIn("ليست احتمال", format_alert(result))

    def test_ignores_unfinished_latest_bar(self):
        self.bars.iloc[-1, self.bars.columns.get_loc("Close")] = 110.
        self.bars.iloc[-1, self.bars.columns.get_loc("High")] = 111.
        self.bars.iloc[-1, self.bars.columns.get_loc("Volume")] = 9999.
        self.assertIsNone(assess_bars("SPY", self.bars, self.now))

    def test_rejects_stale_candles(self):
        self.assertIsNone(assess_bars("SPY", self.bars, self.now + timedelta(hours=3)))

    def test_rejects_naive_timestamps(self):
        naive = self.bars.copy()
        naive.index = naive.index.tz_localize(None)
        self.assertIsNone(assess_bars("SPY", naive, self.now))


if __name__ == "__main__":
    unittest.main()
