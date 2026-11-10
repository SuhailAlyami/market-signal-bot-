import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import numpy as np
import pandas as pd

from backtest_explosion import (
    attach_outcomes,
    build_events,
    evaluate,
    prepare_market,
    scan_early,
    scan_legacy,
    study,
)
from explosion_detector import ExplosionConfig, assess_bars, assess_bars_legacy, regular_hours_start


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

    def test_scanner_matches_online_decisions(self):
        index = pd.date_range("2026-10-16 12:00", periods=120, freq="5min", tz="UTC")
        rng = np.random.default_rng(7)
        close = 100 + np.cumsum(rng.normal(0, 0.05, len(index)))
        open_ = np.r_[close[0], close[:-1]]
        high = np.maximum(open_, close) + 0.05
        low = np.minimum(open_, close) - 0.05
        volume = rng.integers(80, 160, len(index)).astype(float)
        volume[70] = 500
        close[70] = max(close[64:70]) + 0.12
        high[70] = close[70] + 0.05
        open_[70] = close[70] - 0.10
        frame = pd.DataFrame(
            {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
            index=index,
        )
        cfg = ExplosionConfig(mode="early")
        market = prepare_market(frame)
        found = {row["i"]: row for row in scan_early(market, cfg)}
        legacy = {row["i"]: row for row in scan_legacy(market)}
        for i in range(40, len(frame)):
            now = (index[i] + pd.Timedelta(minutes=5, seconds=30)).to_pydatetime()
            early = assess_bars("SPY", frame.iloc[:i + 1], now=now, config=cfg)
            if not regular_hours_start(index[i]):
                self.assertNotIn(i, found)
                self.assertIsNone(early)
            elif i in found:
                self.assertIsNotNone(early)
                self.assertEqual(early["direction"], found[i]["direction"])
                self.assertEqual(early["score"], found[i]["score"])
            else:
                self.assertIsNone(early)
            old = assess_bars_legacy("SPY", frame.iloc[:i + 1], now=now)
            if regular_hours_start(index[i]):
                if i in legacy:
                    self.assertIsNotNone(old)
                    self.assertEqual(old["direction"], legacy[i]["direction"])
                else:
                    self.assertIsNone(old)

    def test_early_signal_leads_the_target_on_a_slow_push(self):
        index = pd.date_range("2026-10-16 13:30", periods=50, freq="5min", tz="UTC")
        frame = pd.DataFrame({
            "Open": np.full(50, 100.0),
            "High": np.full(50, 100.2),
            "Low": np.full(50, 99.8),
            "Close": np.full(50, 100.0),
            "Volume": np.full(50, 100.0),
        }, index=index)
        frame.iloc[40, frame.columns.get_loc("Open")] = 100.10
        frame.iloc[40, frame.columns.get_loc("High")] = 100.45
        frame.iloc[40, frame.columns.get_loc("Low")] = 100.00
        frame.iloc[40, frame.columns.get_loc("Close")] = 100.30
        frame.iloc[40, frame.columns.get_loc("Volume")] = 300.0
        path = [
            (100.30, 100.70, 100.25, 100.60),
            (100.60, 101.05, 100.55, 100.95),
            (100.90, 101.40, 100.85, 101.30),
            (101.30, 101.70, 101.20, 101.55),
        ]
        for offset, (o, h, low, c) in enumerate(path, start=41):
            frame.iloc[offset, frame.columns.get_loc("Open")] = o
            frame.iloc[offset, frame.columns.get_loc("High")] = h
            frame.iloc[offset, frame.columns.get_loc("Low")] = low
            frame.iloc[offset, frame.columns.get_loc("Close")] = c
        market = attach_outcomes(prepare_market(frame))
        sessions = sorted(set(market["day"]))
        early = evaluate(scan_early(market, ExplosionConfig()), build_events(market), market, sessions)
        legacy = evaluate(scan_legacy(market), build_events(market), market, sessions)
        self.assertGreaterEqual(early["median_lead_touch_min"], 10)
        self.assertGreaterEqual(early["median_entry_quality"], 0.5)
        self.assertEqual(legacy["matched_events"], 0)


if __name__ == "__main__":
    unittest.main()
