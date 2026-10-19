"""Safety and lifecycle regressions; these are not prediction-quality evidence."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd

from hunter_runtime import HunterRuntime, NotificationGate, futures_active, validate_completed_bars

UTC = timezone.utc
NOW = datetime(2026, 10, 19, 14, 0, tzinfo=UTC)


def bars(end=NOW, periods=40, price=99.9):
    index = pd.date_range(end=end - timedelta(minutes=1), periods=periods, freq="1min")
    return pd.DataFrame({"Open": price, "High": price + .2, "Low": price - .2,
                         "Close": price, "Volume": 100.}, index=index)


def candidate(data, index):
    return {"direction": 1, "price": float(data.Close.iloc[index]), "atr": 1.,
            "level": 100., "invalidation": 98.9, "rvol": 1.5}


class BarValidationTests(unittest.TestCase):
    def test_complete_bar_only_ignores_unfinished_spike(self):
        frame = bars(NOW + timedelta(minutes=1))
        frame.iloc[-1, frame.columns.get_loc("Close")] = 9000
        data, status = validate_completed_bars(frame, NOW)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(data.Close.iloc[-1], 99.9)
        self.assertEqual(status["last_completed_bar"], NOW.isoformat())

    def test_stale_naive_zero_volume_duplicates_gaps_and_bad_ohlc(self):
        fixtures = []
        fixtures.append((bars(NOW - timedelta(minutes=3)), "stale_feed"))
        naive = bars(); naive.index = naive.index.tz_localize(None)
        fixtures.append((naive, "naive_or_invalid_timestamps"))
        zero = bars(); zero.iloc[-1, zero.columns.get_loc("Volume")] = 0
        fixtures.append((zero, "zero_or_negative_volume"))
        fixtures.append((pd.concat([bars(), bars().iloc[-1:]]), "duplicate_timestamps"))
        fixtures.append((bars().drop(bars().index[-10]), "warming_up_or_gap"))
        invalid = bars(); invalid.iloc[-1, invalid.columns.get_loc("Close")] = 105
        fixtures.append((invalid, "inconsistent_ohlc"))
        invalid = bars(); invalid.iloc[-1, invalid.columns.get_loc("Volume")] = float("inf")
        fixtures.append((invalid, "nonfinite_ohlcv"))
        for frame, expected in fixtures:
            with self.subTest(expected=expected):
                data, status = validate_completed_bars(frame, NOW)
                self.assertIsNone(data)
                self.assertEqual(status["status"], expected)

    def test_opening_minutes_need_full_causal_warmup(self):
        self.assertEqual(validate_completed_bars(bars(periods=30), NOW)[1]["status"], "warming_up_or_gap")
        self.assertEqual(validate_completed_bars(bars(periods=31), NOW)[1]["status"], "ok")

    def test_previous_session_gap_does_not_poison_contiguous_new_session(self):
        frame = pd.concat([bars(NOW - timedelta(days=3)), bars()])
        data, status = validate_completed_bars(frame, NOW)
        self.assertEqual(status["status"], "ok")
        self.assertEqual(len(data), len(frame))  # retain prior-session causal levels

    def test_timezone_and_cme_session_calendar(self):
        # Identical local Sunday 18:00 opening moves one UTC hour with DST.
        self.assertFalse(futures_active(datetime(2026, 10, 18, 21, 59, tzinfo=UTC)))
        self.assertTrue(futures_active(datetime(2026, 10, 18, 22, 0, tzinfo=UTC)))
        self.assertFalse(futures_active(datetime(2026, 11, 8, 22, 59, tzinfo=UTC)))
        self.assertTrue(futures_active(datetime(2026, 11, 8, 23, 0, tzinfo=UTC)))
        self.assertFalse(futures_active(datetime(2026, 10, 17, 14, tzinfo=UTC)))
        self.assertFalse(futures_active(datetime(2026, 10, 19, 21, 15, tzinfo=UTC)))
        # CME removed the 16:15 ET equity-index halt in 2021; calendar knows this.
        self.assertTrue(futures_active(datetime(2026, 10, 19, 20, 20, tzinfo=UTC)))
        self.assertTrue(futures_active(datetime(2026, 11, 26, 17, 59, tzinfo=UTC)))
        self.assertFalse(futures_active(datetime(2026, 11, 26, 18, 1, tzinfo=UTC)))

    def test_naive_now_rejected(self):
        with self.assertRaises(ValueError):
            validate_completed_bars(bars(), NOW.replace(tzinfo=None))


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_path = Path(self.directory.name) / "state.json"
        self.journal = Path(self.directory.name) / "shadow.jsonl"
        self.runtime = self.new_runtime()
        self.frame = bars()

    def new_runtime(self, detector=candidate):
        return HunterRuntime(self.state_path, self.journal, symbols=("ES=F",), detector=detector)

    def poll(self, now=NOW, runtime=None):
        return (runtime or self.runtime).poll(now, lambda symbol: self.frame)

    def append(self, end, close):
        row = bars(end=end, periods=1, price=close)
        self.frame = pd.concat([self.frame, row])

    def records(self):
        return [json.loads(line) for line in self.journal.read_text().splitlines()]

    def test_setup_dedup_survives_process_restart(self):
        first = self.poll()
        self.assertEqual([event["state"] for event in first["events"]], ["SETUP"])
        self.assertFalse(first["events"][0]["notify_eligible"])
        self.assertIsNone(first["events"][0]["confidence_probability"])
        self.assertFalse(first["heartbeat"]["alerts_enabled"])
        self.assertEqual(self.poll()["events"], [])
        self.assertEqual(self.poll(runtime=self.new_runtime())["events"], [])
        self.assertEqual(len([item for item in self.records() if item["record_type"] == "event"]), 1)

    def test_two_close_hysteresis_trigger_exit_cooldown(self):
        self.poll()
        for minute, close in [(1, 100.11), (2, 100.04), (3, 100.11)]:
            self.append(NOW + timedelta(minutes=minute), close)
            self.assertEqual(self.poll(NOW + timedelta(minutes=minute))["events"], [])
        self.append(NOW + timedelta(minutes=4), 100.12)
        triggered = self.poll(NOW + timedelta(minutes=4))
        self.assertEqual(triggered["events"][0]["state"], "TRIGGER")
        self.append(NOW + timedelta(minutes=5), 98.5)
        self.assertEqual(self.poll(NOW + timedelta(minutes=5))["events"][0]["state"], "EXIT")
        self.append(NOW + timedelta(minutes=6), 99.9)
        self.assertEqual(self.poll(NOW + timedelta(minutes=6))["events"], [])
        self.append(NOW + timedelta(minutes=10), 99.9)
        # A gap is fail-closed, so missing cooldown candles cannot be invented.
        self.assertEqual(self.poll(NOW + timedelta(minutes=10))["heartbeat"]["status"], "degraded")

    def test_setup_invalidation_and_expiry(self):
        self.poll()
        self.append(NOW + timedelta(minutes=1), 98.8)
        self.assertEqual(self.poll(NOW + timedelta(minutes=1))["events"][0]["state"], "INVALIDATION")
        other = Path(self.directory.name) / "expiry.json"
        runtime = HunterRuntime(other, self.journal, symbols=("ES=F",), detector=candidate)
        self.frame = bars()
        self.poll(runtime=runtime)
        for minute in range(1, 11):
            self.append(NOW + timedelta(minutes=minute), 99.9)
            result = self.poll(NOW + timedelta(minutes=minute), runtime)
        self.assertEqual(result["events"][0]["reason"], "scenario_expired")

    def test_stale_feed_invalidates_and_heartbeat_exposes_last_completed_bar(self):
        self.poll()
        result = self.poll(NOW + timedelta(minutes=3))
        self.assertEqual(result["heartbeat"]["status"], "degraded")
        status = result["heartbeat"]["symbols"]["ES=F"]
        self.assertEqual(status["status"], "stale_feed")
        self.assertEqual(status["last_completed_bar"], NOW.isoformat())
        self.assertEqual(result["events"][0]["state"], "INVALIDATION")
        self.assertIsNone(result["events"][0]["price"])

    def test_one_provider_failure_never_hides_other_symbol_or_outage(self):
        runtime = HunterRuntime(self.state_path, self.journal, detector=candidate)
        seen = []
        def fetch(symbol):
            seen.append(symbol)
            if symbol == "ES=F":
                raise TimeoutError("private details must not be printed")
            return self.frame
        result = runtime.poll(NOW, fetch)
        self.assertEqual(seen, ["ES=F", "NQ=F"])
        self.assertEqual(result["heartbeat"]["symbols"]["ES=F"]["status"], "provider_error")
        self.assertEqual(result["events"][0]["symbol"], "NQ=F")
        self.assertNotIn("private details", json.dumps(result))

    def test_later_outcome_is_measured_without_option_pnl(self):
        setup = self.poll()["events"][0]
        self.assertFalse(any(item["record_type"] == "outcome" for item in self.records()))
        for minute in range(1, 6):
            self.append(NOW + timedelta(minutes=minute), 99.9 + minute / 10)
            self.poll(NOW + timedelta(minutes=minute))
        outcomes = [item for item in self.records() if item["record_type"] == "outcome" and item["event_id"] == setup["event_id"]]
        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0]["status"], "observed")
        self.assertAlmostEqual(outcomes[0]["underlying_return_bps"], (.4 / 100.) * 10000)
        self.assertEqual(outcomes[0]["entry_reference_price"], 100.)
        self.assertIsNone(outcomes[0]["option_pnl"])
        self.assertFalse(outcomes[0]["execution_assumed"])

    def test_notification_cap_only_limits_delivery_and_reservation_survives_restart(self):
        result = self.poll()
        gate = NotificationGate(self.runtime, max_daily=1, cooldown_seconds=0)
        # Experimental event can never pass even an available quota.
        self.assertFalse(gate.reserve(result["events"][0], NOW))
        reviewed = {**result["events"][0], "notify_eligible": True}
        self.assertTrue(gate.reserve(reviewed, NOW))
        self.assertFalse(NotificationGate(self.new_runtime(), max_daily=1, cooldown_seconds=0).reserve(reviewed, NOW))
        self.append(NOW + timedelta(minutes=1), 98.5)
        new_result = self.poll(NOW + timedelta(minutes=1))
        self.assertEqual(new_result["events"][0]["state"], "INVALIDATION")
        self.assertFalse(gate.reserve({**new_result["events"][0], "notify_eligible": True}, NOW + timedelta(minutes=1)))

    def test_corrupt_or_malformed_state_fails_closed(self):
        for value in ("not json", "[]", "null", '{"version":1,"symbols":{"ES=F":[]},"pending":[],"notifications":{}}',
                      '{"version":1,"symbols":{},"pending":[{"bad":1}],"notifications":{}}'):
            self.state_path.write_text(value)
            runtime = self.new_runtime()
            fetch = Mock()
            result = runtime.poll(NOW, fetch)
            self.assertEqual(result["heartbeat"]["status"], "state_unreadable")
            self.assertEqual(result["events"], [])
            fetch.assert_not_called()

    def test_calendar_outage_is_observable(self):
        with patch("hunter_runtime.futures_active", side_effect=ImportError):
            result = self.poll()
        self.assertEqual(result["heartbeat"]["status"], "calendar_unavailable")
        self.assertEqual(result["heartbeat"]["symbols"]["ES=F"]["status"], "calendar_unavailable")

    def test_detector_failure_is_observable(self):
        def broken(data, index):
            raise RuntimeError("no detector")
        runtime = self.new_runtime(broken)
        result = self.poll(runtime=runtime)
        self.assertEqual(result["heartbeat"]["symbols"]["ES=F"]["status"], "detector_error")
        self.assertEqual(result["heartbeat"]["status"], "degraded")

    def test_render_health_distinguishes_not_started_fresh_and_stalled(self):
        import globex_render_worker as worker
        with patch.object(worker, "_STATUS", {"status": "not_started", "alerts_enabled": False}):
            self.assertEqual(worker.get_status(NOW)["status"], "not_started")
        heartbeat = {"status": "ok", "timestamp": NOW.isoformat(), "alerts_enabled": False}
        with patch.object(worker, "_STATUS", heartbeat):
            self.assertEqual(worker.get_status(NOW)["heartbeat_age_seconds"], 0)
            self.assertEqual(worker.get_status(NOW + timedelta(minutes=4))["status"], "worker_stalled")

    def test_polling_gap_cancels_active_setup_instead_of_joining_skipped_closes(self):
        self.poll()
        self.append(NOW + timedelta(minutes=1), 100.2)
        self.poll(NOW + timedelta(minutes=1))
        # A pause hid both a failed confirmation and an invalidating close.
        for minute, close in [(2, 100.04), (3, 98.5), (4, 100.2), (5, 100.2), (6, 100.2)]:
            self.append(NOW + timedelta(minutes=minute), close)
        restarted = self.new_runtime()
        result = self.poll(NOW + timedelta(minutes=6), restarted)
        self.assertEqual([item["state"] for item in result["events"]], ["INVALIDATION"])
        self.assertEqual(result["events"][0]["reason"], "missed_polling_bars")
        self.assertEqual(result["heartbeat"]["status"], "degraded")

    def test_delayed_detection_outcome_excludes_predetection_returns(self):
        detected = NOW + timedelta(minutes=1, seconds=30)
        setup = self.poll(detected)["events"][0]
        # Large gap already happened before the actual decision. It must not
        # become a profitable shadow outcome from the old 99.9 candle close.
        for minute in range(1, 8):
            self.append(NOW + timedelta(minutes=minute), 110.)
        self.poll(NOW + timedelta(minutes=7))
        outcome = next(item for item in self.records() if item["record_type"] == "outcome" and item["event_id"] == setup["event_id"])
        self.assertEqual(outcome["outcome_start"], (NOW + timedelta(minutes=2)).isoformat())
        self.assertEqual(outcome["underlying_return_bps"], 0.)
        self.assertEqual(outcome["entry_reference_price"], 110.)

    def test_live_receipt_timestamp_includes_provider_request_time(self):
        received = NOW + timedelta(seconds=3)
        result = self.runtime.poll(NOW, lambda symbol: self.frame, clock=lambda: received)
        self.assertEqual(result["events"][0]["detected_at"], received.isoformat())
        self.assertEqual(result["events"][0]["detection_delay_seconds"], 3.)
        self.assertEqual(result["heartbeat"]["poll_started_at"], NOW.isoformat())
        self.assertEqual(result["heartbeat"]["timestamp"], received.isoformat())

    def test_slow_fetch_crossing_market_close_cannot_generate_setup(self):
        start = datetime(2026, 10, 19, 20, 59, 59, tzinfo=UTC)
        receipt = start + timedelta(seconds=21)
        self.frame = bars(datetime(2026, 10, 19, 21, 0, tzinfo=UTC))
        result = self.runtime.poll(start, lambda symbol: self.frame, clock=lambda: receipt)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["heartbeat"]["symbols"]["ES=F"]["status"], "closed")

    def test_calendar_lookup_failure_after_fetch_remains_fail_closed(self):
        with patch("hunter_runtime.futures_active", side_effect=[True, ImportError]):
            result = self.poll()
        self.assertEqual(result["events"], [])
        self.assertEqual(result["heartbeat"]["status"], "calendar_unavailable")


if __name__ == "__main__":
    unittest.main()
