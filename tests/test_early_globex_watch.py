import unittest
from datetime import datetime, timezone
import pandas as pd
from early_globex_watch import detect_early, globex_active

UTC = timezone.utc

class EarlyGlobexWatchTests(unittest.TestCase):
    def test_sunday_globex_opens_at_18_et(self):
        self.assertFalse(globex_active(datetime(2026, 10, 18, 21, 59, tzinfo=UTC)))
        self.assertTrue(globex_active(datetime(2026, 10, 18, 22, 0, tzinfo=UTC)))

    def test_stale_bars_rejected(self):
        idx = pd.date_range("2026-10-18T22:00:00Z", periods=14, freq="5min")
        data = pd.DataFrame({"High": [100]*13+[105], "Low": [99]*14,
                             "Close": [99.5]*13+[104], "Volume": [100]*13+[250]}, index=idx)
        self.assertIsNotNone(detect_early("ES=F", data, datetime(2026, 10, 18, 23, 10, tzinfo=UTC)))
        self.assertIsNone(detect_early("ES=F", data, datetime(2026, 10, 18, 23, 30, tzinfo=UTC)))

    def test_incomplete_bar_never_used(self):
        idx = pd.date_range("2026-10-18T22:00:00Z", periods=14, freq="5min")
        data = pd.DataFrame({"High": [100]*13+[105], "Low": [99]*14,
                             "Close": [99.5]*13+[104], "Volume": [100]*13+[250]}, index=idx)
        self.assertIsNone(detect_early("ES=F", data, datetime(2026, 10, 18, 23, 5, tzinfo=UTC)))

    def test_breakout_detected_in_first_half_hour(self):
        idx = pd.date_range("2026-10-18T22:00:00Z", periods=5, freq="5min")
        data = pd.DataFrame({"High": [100,100,100,100,103],
                             "Low": [99]*5, "Close": [99.5]*4+[102],
                             "Volume": [100]*4+[220]}, index=idx)
        item = detect_early("ES=F", data, datetime(2026, 10, 18, 22, 25, tzinfo=UTC))
        self.assertIsNotNone(item)
        self.assertEqual(item["direction"], "WATCH_UP")

    def test_opening_breakout_rejects_low_volume(self):
        idx = pd.date_range("2026-10-18T22:00:00Z", periods=5, freq="5min")
        data = pd.DataFrame({"High": [100]*4+[103],
                             "Low": [99]*5, "Close": [99.5]*4+[102],
                             "Volume": [100]*4+[105]}, index=idx)
        self.assertIsNone(detect_early("ES=F", data, datetime(2026, 10, 18, 22, 25, tzinfo=UTC)))

if __name__ == "__main__":
    unittest.main()
