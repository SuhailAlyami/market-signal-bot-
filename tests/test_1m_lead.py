import unittest
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from research_1m_lead import (
    CONTEXT_PROMOTED,
    build_events,
    context_signals,
    five_minute_atr,
    legacy_signals,
    promote,
    split_sessions,
)


def _session(day: str, price: float = 100.0, minutes: int = 60) -> pd.DataFrame:
    start = pd.Timestamp(f"{day} 13:30", tz="UTC")
    index = pd.date_range(start, periods=minutes, freq="1min")
    frame = pd.DataFrame({
        "Open": np.full(minutes, price),
        "High": np.full(minutes, price + 0.04),
        "Low": np.full(minutes, price - 0.04),
        "Close": np.full(minutes, price),
        "Volume": np.full(minutes, 100.0),
    }, index=index)
    return frame


class OneMinuteLeadTests(unittest.TestCase):
    def _market(self):
        first = _session("2026-10-19", minutes=120)
        second = _session("2026-10-20", minutes=80)
        # Fifth completed minute (13:34 UTC = 09:34 EDT) is a small continuation.
        second.iloc[4, second.columns.get_loc("Open")] = 100.05
        second.iloc[4, second.columns.get_loc("High")] = 100.072
        second.iloc[4, second.columns.get_loc("Close")] = 100.07
        # The explosion starts later and finishes inside 30 minutes.
        for offset, close in enumerate(np.linspace(100.08, 100.45, 16), start=20):
            second.iloc[offset, second.columns.get_loc("Open")] = close - 0.02
            second.iloc[offset, second.columns.get_loc("High")] = close + 0.02
            second.iloc[offset, second.columns.get_loc("Close")] = close
        frame = pd.concat([first, second]).sort_index()
        vix = frame[["Close"]].copy()
        vix["Close"] = 18.0
        vix["Open"] = vix["High"] = vix["Low"] = 18.0
        vix["Volume"] = 0.0
        return frame, {"^VIX": vix, "^VIX1D": vix.copy(), "^NYA": frame.copy()}

    def test_open_drive_is_before_the_later_push_and_ignores_the_future(self):
        frame, aux = self._market()
        atr = five_minute_atr(frame)
        signals = context_signals(frame, aux, atr)["open_drive"]
        self.assertTrue(any(row["day"].isoformat() == "2026-10-20" and row["direction"] == "BULLISH" for row in signals))
        signal = next(row for row in signals if row["day"].isoformat() == "2026-10-20")
        events = build_events(frame, atr)
        later = [event for event in events if event["day"].isoformat() == "2026-10-20" and event["direction"] == "BULLISH"]
        self.assertTrue(later)
        self.assertLess(signal["decision_net"], later[0]["onset"])
        extra = frame.copy()
        future = pd.DataFrame(
            {"Open": [150.0], "High": [160.0], "Low": [149.0], "Close": [155.0], "Volume": [5000.0]},
            index=pd.DatetimeIndex([frame.index[-1] + pd.Timedelta(minutes=1)]),
        )
        extra = pd.concat([extra, future])
        again = context_signals(extra, aux, five_minute_atr(extra))["open_drive"]
        before = [row["bar_start"] for row in signals]
        self.assertEqual(before, [row["bar_start"] for row in again if row["bar_start"] <= frame.index[-1]])

    def test_recent_vix_spike_is_not_visible_until_the_lag_expires(self):
        frame, aux = self._market()
        vix = aux["^VIX"].copy()
        # Spike on the latest bars: a 15-minute lag must hide it.
        vix.iloc[-5:, vix.columns.get_loc("Close")] = 19.0
        aux = {**aux, "^VIX": vix}
        atr = five_minute_atr(frame)
        fresh = context_signals(frame, aux, atr)["vix_lag15"]
        self.assertEqual(fresh, [])
        lagged = vix.copy()
        lagged["Close"] = 18.0
        # A move that ended more than 15 minutes before the last bar.
        lagged.iloc[-25:-20, lagged.columns.get_loc("Close")] = 18.3
        aux = {**aux, "^VIX": lagged}
        seen = context_signals(frame, aux, five_minute_atr(frame))["vix_lag15"]
        spike_known = lagged.index[-25] + pd.Timedelta(minutes=1)
        bears = [row for row in seen if row["direction"] == "BEARISH"]
        self.assertTrue(bears)
        self.assertTrue(all(row["bar_end"] - spike_known >= pd.Timedelta(minutes=15) for row in bears))

    def test_share_cost_reduces_entry_quality(self):
        from research_1m_lead import evaluate
        index = pd.date_range("2026-10-20 13:30", periods=40, freq="1min", tz="UTC")
        frame = pd.DataFrame({
            "Open": np.full(40, 100.0), "High": np.linspace(100.1, 101.0, 40),
            "Low": np.full(40, 99.9), "Close": np.linspace(100.0, 100.8, 40), "Volume": np.full(40, 100.0),
        }, index=index)
        signal = {
            "name": "sample", "day": index[0].tz_convert("America/New_York").date(),
            "bar_start": index[2], "bar_end": index[2] + pd.Timedelta(minutes=1),
            "decision_gross": index[2] + pd.Timedelta(minutes=1),
            "decision_net": index[2] + pd.Timedelta(minutes=2),
            "direction": "BULLISH", "close": 100.1, "entry_gross": 100.1, "entry_net": 100.11,
            "atr": 0.05,
        }
        event = {
            "onset": index[8], "touch": index[20], "direction": "BULLISH",
            "p0": 100.0, "extreme": 101.0, "target": 0.3, "atr": 0.05,
            "day": signal["day"],
        }
        gross = evaluate([signal], [event], frame, [signal["day"]], "gross")
        net = evaluate([signal], [event], frame, [signal["day"]], "net")
        self.assertGreater(gross["median_entry_quality"], net["median_entry_quality"])
        self.assertGreater(gross["median_lead_min"], net["median_lead_min"])

    def test_split_is_chronological_and_macro_is_not_every_day(self):
        days = [datetime(2026, 10, 19).date() + timedelta(days=i) for i in range(16)]
        parts = split_sessions(days)
        self.assertLess(parts["train"][-1], parts["validation"][0])
        self.assertLess(parts["validation"][-1], parts["test"][0])
        self.assertEqual(len(parts["test"]), 4)
        self.assertEqual(len(parts["validation"]), 4)
        frame, aux = self._market()
        signals = context_signals(frame, aux, five_minute_atr(frame))["macro_release"]
        self.assertEqual(signals, [])

    def test_promotion_requires_non_overlapping_recall_intervals(self):
        legacy = {
            "recall_before_onset_wilson95": [0.05, 0.20],
            "median_entry_quality": 0.4,
            "false_alarms_per_session": 1.0,
            "forward_hit_wilson95": [0.10, 0.30],
        }
        weak = {
            "recall_before_onset_wilson95": [0.15, 0.40],
            "median_entry_quality": 0.5,
            "false_alarms_per_session": 1.1,
            "forward_hit_wilson95": [0.12, 0.35],
        }
        strong = {
            "recall_before_onset_wilson95": [0.25, 0.55],
            "median_entry_quality": 0.5,
            "false_alarms_per_session": 1.1,
            "forward_hit_wilson95": [0.12, 0.35],
        }
        self.assertFalse(promote(weak, legacy)["promote"])
        self.assertTrue(promote(strong, legacy)["promote"])
        self.assertFalse(CONTEXT_PROMOTED)

    def test_legacy_confirmation_still_needs_the_large_move(self):
        frame, _ = self._market()
        self.assertEqual(legacy_signals(frame), [])


if __name__ == "__main__":
    unittest.main()
