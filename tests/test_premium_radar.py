from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from premium_radar import assess_history, classify, history_frame, journal_observations
from research_premium_radar import evaluate, study


def bars(n=30):
    index = pd.date_range("2026-10-20T14:00:00Z", periods=n, freq="min")
    return pd.DataFrame({"Open": 10., "High": 10.4, "Low": 9.6,
                         "Close": 10., "Volume": 100.}, index=index)


def raw(data):
    return {"chart_step": 60, "time": [x.isoformat() for x in data.index],
            **{key.lower(): data[key].tolist() for key in data.columns}}


class PremiumRadarTests(unittest.TestCase):
    def test_watch_precedes_breakout_and_has_no_probability_or_fill(self):
        data = bars(21)
        data.iloc[20] = [10.1, 10.35, 10., 10.3, 160.]
        signal = classify(data, 20)
        self.assertEqual(signal["state"], "WATCH")
        self.assertLess(signal["reference_trade_price"], signal["breakout_level"])
        self.assertIsNone(signal["probability"])
        self.assertIsNone(signal["execution_price"])
        self.assertFalse(signal["notifications_enabled"])

    def test_first_completed_acceleration_minute(self):
        data = bars(21)
        data.iloc[20] = [10., 11.1, 10., 11., 200.]
        self.assertEqual(classify(data, 20)["state"], "ACCELERATION")

    def test_no_future_leakage(self):
        data = bars(30)
        data.iloc[20] = [10., 11.1, 10., 11., 200.]
        expected = classify(data.iloc[:21], 20)
        data.iloc[21:] = [100., 110., 90., 105., 100000.]
        self.assertEqual(classify(data, 20), expected)

    def test_no_signal_for_zero_volume_bad_prices_or_gap(self):
        for key, value in (("Volume", 0), ("Close", float("nan")), ("Low", -1), ("High", 1)):
            data = bars(21)
            data.iloc[20] = [10., 11.1, 10., 11., 200.]
            data.loc[data.index[-1], key] = value
            self.assertIsNone(classify(data, 20))
        data = bars(22).drop(bars(22).index[10])
        self.assertIsNone(classify(data, 20))

    def test_thin_trade_window_rejected(self):
        data = bars(21)
        data.iloc[:15, data.columns.get_loc("Volume")] = 0
        data.iloc[20] = [10., 11.1, 10., 11., 200.]
        self.assertIsNone(classify(data, 20))

    def test_unfinished_bar_cannot_trigger(self):
        data = bars(22)
        data.iloc[21] = [10., 11.1, 10., 11., 200.]
        result = assess_history(raw(data), now=data.index[21].to_pydatetime() + timedelta(seconds=30),
                                feed_status="REALTIME")
        self.assertEqual(result["status"], "observed")
        self.assertIsNone(result["signal"])

    def test_stale_delayed_frozen_histories_cannot_signal(self):
        data = bars(21)
        data.iloc[20] = [10., 11.1, 10., 11., 200.]
        now = data.index[-1].to_pydatetime() + timedelta(minutes=1)
        for state in ("DELAYED", "FROZEN", "UNAVAILABLE"):
            self.assertIsNone(assess_history(raw(data), now=now, feed_status=state)["signal"])
        delayed = raw(data)
        delayed["delayed"] = 1
        self.assertIsNone(assess_history(delayed, now=now, feed_status="REALTIME")["signal"])
        self.assertIsNone(assess_history(raw(data), now=now+timedelta(minutes=3), feed_status="REALTIME")["signal"])

    def test_reject_mismatched_and_naive_history(self):
        data = raw(bars())
        data["volume"] = []
        with self.assertRaises(ValueError):
            history_frame(data)
        data = raw(bars())
        data["time"] = [x.replace("+00:00", "") for x in data["time"]]
        with self.assertRaises(ValueError):
            history_frame(data)


class PremiumResearchTests(unittest.TestCase):
    def test_early_lead_and_delay_penalty_are_measured(self):
        data = bars(35)
        data.iloc[20] = [10.1, 10.35, 10., 10.3, 160.]
        data.iloc[21] = [10.3, 10.4, 10.2, 10.35, 100.]
        data.iloc[22] = [10.35, 11.6, 10.35, 11.5, 200.]
        data.iloc[23] = [11.5, 14., 11.5, 13.5, 200.]
        immediate = evaluate(data)
        delayed = evaluate(data, delay_seconds=120)
        self.assertGreater(immediate["independent_events"], 0)
        self.assertGreater(immediate["methods"]["radar_watch"]["early_events"], 0)
        self.assertEqual(delayed["methods"]["radar_watch"]["early_events"], 0)

    def test_small_sample_does_not_claim_holdout_success(self):
        report = study(raw(bars(40)))
        self.assertEqual(report["decision"], "NOT_READY")
        self.assertIsNone(report["holdout"])
        self.assertEqual(report["reason"], "insufficient_sessions_for_train_validation_holdout")


class JournalTests(unittest.TestCase):
    def observation(self, minute=21):
        data = bars(21)
        data.iloc[20] = [10.1, 10.35, 10., 10.3, 160.]
        when = data.index[0].to_pydatetime() + timedelta(minutes=minute)
        item = {"expiry": "2026-10-20", "strike": 7690., "side": "CALL",
                **assess_history(raw(data), now=when, feed_status="REALTIME")}
        return {"observed_at": when.isoformat(), "premium_radar": [item]}

    def test_dedupe_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.observation()
            self.assertEqual(len(journal_observations(report, directory)), 1)
            self.assertEqual(journal_observations(report, directory), [])
            rows = (Path(directory) / "premium_shadow.jsonl").read_text().splitlines()
            self.assertEqual(len(rows), 1)
            self.assertFalse(json.loads(rows[0])["notifications_enabled"])

    def test_provider_outage_cancels_without_fabricating_price(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.observation()
            journal_observations(report, directory)
            report["premium_radar"] = []
            result = journal_observations(report, directory)
            self.assertEqual(result[0]["state"], "INVALIDATION")
            self.assertIsNone(result[0]["reference_trade_price"])

    def test_level_invalidation(self):
        with tempfile.TemporaryDirectory() as directory:
            report = self.observation()
            journal_observations(report, directory)
            report["premium_radar"][0].update(signal=None, reference_trade_price=9.)
            result = journal_observations(report, directory)
            self.assertEqual(result[0]["state"], "INVALIDATION")

    def test_corrupt_state_never_silently_resets_dedupe(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "premium_state.json").write_text("broken")
            with self.assertRaises(ValueError):
                journal_observations(self.observation(), directory)
