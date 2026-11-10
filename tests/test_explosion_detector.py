import unittest
from unittest.mock import patch, Mock
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from explosion_detector import (
    ExplosionConfig,
    assess_bars,
    assess_bars_legacy,
    config_from_env,
    format_alert,
    market_session_open,
    reserve_once,
)


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

    def _early_release(self):
        bars = self.bars.copy()
        loc = -2
        bars.iloc[loc, bars.columns.get_loc("Open")] = 100.10
        bars.iloc[loc, bars.columns.get_loc("High")] = 100.45
        bars.iloc[loc, bars.columns.get_loc("Low")] = 100.00
        bars.iloc[loc, bars.columns.get_loc("Close")] = 100.30
        bars.iloc[loc, bars.columns.get_loc("Volume")] = 300.
        return bars

    def test_early_release_fires_before_a_large_extension(self):
        result = assess_bars("SPY", self._early_release(), self.now, config=ExplosionConfig(mode="early"))
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"], "BULLISH")
        self.assertEqual(result["state"], "SETUP")
        self.assertLessEqual(result["extension_atr"], 0.35)
        text = format_alert(result)
        self.assertIn("ليست احتمال", text)
        self.assertIn("استعداد", text)
        self.assertIn("ليست توصية", text)

    def test_extended_bar_is_not_an_entry_but_legacy_still_confirms_it(self):
        self.bars.iloc[-2, self.bars.columns.get_loc("Close")] = 103.
        self.bars.iloc[-2, self.bars.columns.get_loc("High")] = 103.2
        self.bars.iloc[-2, self.bars.columns.get_loc("Volume")] = 500.
        self.assertIsNone(assess_bars("SPY", self.bars, self.now, config=ExplosionConfig(mode="early")))
        legacy = assess_bars_legacy("SPY", self.bars, self.now)
        self.assertIsNotNone(legacy)
        self.assertEqual(legacy["direction"], "BULLISH")
        widened = assess_bars(
            "SPY", self.bars, self.now,
            config=ExplosionConfig(mode="early", ext_max_atr=8.0),
        )
        self.assertIsNotNone(widened)
        shipped = assess_bars("SPY", self.bars, self.now, config=ExplosionConfig())
        self.assertEqual(shipped["direction"], "BULLISH")
        self.assertEqual(shipped["reason"], "legacy_30bar_confirmation")
        self.assertIn("دخول مشروط", format_alert(shipped))

    def test_default_extension_cap_stays_early(self):
        self.assertLessEqual(ExplosionConfig().ext_max_atr, 1.0)

    def test_cooldown_suppresses_the_next_same_direction_bar(self):
        bars = self._early_release()
        bars.iloc[-3, bars.columns.get_loc("Open")] = 100.10
        bars.iloc[-3, bars.columns.get_loc("High")] = 100.45
        bars.iloc[-3, bars.columns.get_loc("Low")] = 100.00
        bars.iloc[-3, bars.columns.get_loc("Close")] = 100.30
        bars.iloc[-3, bars.columns.get_loc("Volume")] = 300.
        bars.iloc[-2, bars.columns.get_loc("Open")] = 100.35
        bars.iloc[-2, bars.columns.get_loc("High")] = 100.70
        bars.iloc[-2, bars.columns.get_loc("Low")] = 100.30
        bars.iloc[-2, bars.columns.get_loc("Close")] = 100.55
        bars.iloc[-2, bars.columns.get_loc("Volume")] = 300.
        self.assertIsNone(assess_bars("SPY", bars, self.now, config=ExplosionConfig(mode="early")))
        first_now = bars.index[-3].to_pydatetime() + timedelta(minutes=5, seconds=30)
        first = assess_bars("SPY", bars.iloc[:-2], first_now, config=ExplosionConfig(mode="early"))
        self.assertIsNotNone(first)

    def test_overnight_gap_is_not_a_breakout(self):
        bars = self._early_release()
        shifted = bars.index.to_series().copy()
        shifted.iloc[:-8] = shifted.iloc[:-8] - pd.Timedelta(days=1)
        bars.index = pd.DatetimeIndex(shifted)
        self.assertIsNone(assess_bars("SPY", bars, self.now, config=ExplosionConfig(mode="early")))

    def test_future_bars_do_not_change_the_signal(self):
        bars = self._early_release()
        original = assess_bars("SPY", bars, self.now, config=ExplosionConfig(mode="early"))
        extra = bars.copy()
        future_time = extra.index[-1] + pd.Timedelta(minutes=5)
        future = pd.DataFrame(
            {"Open": [150.], "High": [160.], "Low": [149.], "Close": [155.], "Volume": [9000.]},
            index=pd.DatetimeIndex([future_time]),
        )
        extra = pd.concat([extra, future])
        again = assess_bars("SPY", extra, self.now, config=ExplosionConfig(mode="early"))
        self.assertEqual(original["bar_time"], again["bar_time"])
        self.assertEqual(original["direction"], again["direction"])
        self.assertEqual(original["price"], again["price"])

    def test_environment_can_raise_the_volume_gate(self):
        with patch.dict("os.environ", {"EXPLOSION_MODE": "early", "EXPLOSION_RVOL_MIN": "50"}, clear=False):
            self.assertEqual(config_from_env().mode, "early")
            self.assertEqual(config_from_env().rvol_min, 50.0)
            self.assertIsNone(assess_bars("SPY", self._early_release(), self.now))
        late = self.bars.copy()
        late.iloc[-2, late.columns.get_loc("Close")] = 103.
        late.iloc[-2, late.columns.get_loc("High")] = 103.2
        late.iloc[-2, late.columns.get_loc("Volume")] = 500.
        with patch.dict("os.environ", {"EXPLOSION_LEGACY_MOMENTUM_PCT": "10"}, clear=False):
            self.assertIsNone(assess_bars("SPY", late, self.now))
        self.assertIsNotNone(assess_bars("SPY", late, self.now, config=ExplosionConfig()))

    def test_calendar_handles_holiday_and_dst(self):
        holiday = datetime(2026, 11, 26, 15, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertFalse(market_session_open(holiday))
        summer = datetime(2026, 7, 15, 14, 0, tzinfo=timezone.utc)
        winter = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
        self.assertTrue(market_session_open(summer))
        self.assertTrue(market_session_open(winter))

    def test_ignores_unfinished_latest_bar(self):
        self.bars.iloc[-1, self.bars.columns.get_loc("Close")] = 110.
        self.bars.iloc[-1, self.bars.columns.get_loc("High")] = 111.
        self.bars.iloc[-1, self.bars.columns.get_loc("Volume")] = 9999.
        self.assertIsNone(assess_bars("SPY", self.bars, self.now))

    def test_rejects_stale_candles(self):
        self.assertIsNone(assess_bars("SPY", self.bars, self.now + timedelta(hours=3)))

    def test_dedup_fails_closed_without_token(self):
        with patch.dict("os.environ", {"GITHUB_TOKEN": "", "GITHUB_REPOSITORY": ""}):
            self.assertFalse(reserve_once({
                "symbol": "SPY", "direction": "BULLISH", "bar_time": "2026-10-16T19:00:00+00:00"
            }))

    def test_duplicate_candle_is_suppressed(self):
        key = "SPY:BULLISH:2026-10-16T19:00:00+00:00"
        response = Mock()
        response.json.return_value = [{"title": "[Suhail Hunter State] SPY", "body": key}]
        with patch.dict("os.environ", {"GITHUB_TOKEN": "dummy", "GITHUB_REPOSITORY": "x/y"}):
            with patch("explosion_detector.requests.get", return_value=response):
                with patch("explosion_detector.requests.post") as send:
                    self.assertFalse(reserve_once({
                        "symbol": "SPY", "direction": "BULLISH", "bar_time": "2026-10-16T19:00:00+00:00"
                    }))
                    send.assert_not_called()

    def test_rejects_naive_timestamps(self):
        naive = self.bars.copy()
        naive.index = naive.index.tz_localize(None)
        self.assertIsNone(assess_bars("SPY", naive, self.now))


if __name__ == "__main__":
    unittest.main()
