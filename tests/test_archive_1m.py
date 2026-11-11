import tempfile
import unittest
import unittest.mock
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from archive_1m import (
    HistoryOutcome,
    IBKR_SPECS,
    Pacer,
    append_live,
    backoff_seconds,
    closed_session_days,
    collect_ibkr,
    day_ready,
    is_pacing_error,
    is_permission_error,
    run_backfill,
    store_days,
)


def _bar(when: str = "2026-11-09T15:00:00+00:00", price: float = 100.0,
        received: str = "2026-11-09T21:10:00+00:00", timing: str = "historical_batch"):
    return {
        "timestamp": datetime.fromisoformat(when),
        "Open": price, "High": price + 0.1, "Low": price - 0.1, "Close": price,
        "Volume": 10.0,
        "received_at": datetime.fromisoformat(received),
        "timing": timing,
    }


class ArchiveTests(unittest.TestCase):
    def test_day_waits_until_extended_close(self):
        noon = datetime(2026, 11, 9, 17, 0, tzinfo=timezone.utc)  # 12:00 EST
        self.assertFalse(day_ready(noon.astimezone(ZoneInfo("America/New_York")).date(), noon))
        after = datetime(2026, 11, 10, 1, 15, tzinfo=timezone.utc)  # 20:15 EST on Nov 9
        self.assertTrue(day_ready(datetime(2026, 11, 9).date(), after))
        self.assertFalse(day_ready(datetime(2026, 11, 10).date(), after))

    def test_existing_day_is_not_replaced(self):
        # 2026-11-09 15:00 UTC = 10:00 EST, inside the session.
        first = _bar("2026-11-09T15:00:00+00:00", 100.0)
        now = datetime(2026, 11, 10, 1, 20, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            stored = store_days(folder, [first], now)
            self.assertEqual(len(stored["stored"]), 1)
            again = store_days(folder, [_bar("2026-11-09T15:00:00+00:00", 250.0)], now)
            self.assertEqual(again["conflicts"], ["2026-11-09"])
            self.assertEqual(again["stored"], [])
            same = store_days(folder, [first], now)
            self.assertEqual(same["unchanged"], ["2026-11-09"])

    def test_permission_error_does_not_drop_other_symbols(self):
        now = datetime(2026, 11, 10, 1, 20, tzinfo=timezone.utc)
        spy = HistoryOutcome()
        spy.bars = [_bar("2026-11-09T15:00:00+00:00", 500.0)]
        spy.live_bars = [_bar("2026-11-09T15:01:00+00:00", 501.0, "2026-11-09T15:01:05+00:00", "live_update")]
        denied = HistoryOutcome()
        denied.errors = [{"code": 354, "message": "Requested market data is not subscribed"}]
        empty = HistoryOutcome()
        empty.errors = [{"code": 162, "message": "HMDS query returned no data"}]
        midpoint = HistoryOutcome()
        midpoint.bars = [_bar("2026-11-09T15:00:00+00:00", 5800.0)]

        class Fake:
            market_data_type = None

            def set_market_data_type(self, kind):
                self.market_data_type = kind

            def history(self, spec, use_rth, what_to_show):
                self.last = (spec["folder"], what_to_show, use_rth)
                if spec["folder"] == "VIX":
                    return denied
                if spec["folder"] == "SPX" and what_to_show == "TRADES":
                    return empty
                if spec["folder"] == "SPX":
                    return midpoint
                if spec["folder"] == "SPY" and what_to_show == "TRADES":
                    return spy
                return HistoryOutcome()

        with tempfile.TemporaryDirectory() as tmp:
            report = collect_ibkr(Fake(), Path(tmp), now, use_rth=0)
            self.assertEqual([item["symbol"] for item in report["permission_missing"]], ["VIX"])
            self.assertTrue(any(item["folder"] == "SPY" for item in report["stored"]))
            self.assertTrue(any(item["folder"] == "SPX" for item in report["stored"]))
            self.assertEqual(report["live_appended"], 1)
            text = (Path(tmp) / "ibkr" / "SPY" / "live-2026-11-09.jsonl").read_text(encoding="utf-8")
            self.assertIn("15:01:05", text)

    def test_live_timestamp_is_not_duplicated(self):
        row = _bar("2026-11-09T15:01:00+00:00", 501.0, "2026-11-09T15:01:05+00:00", "live_update")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            self.assertEqual(append_live(folder, [row]), 1)
            self.assertEqual(append_live(folder, [row]), 0)

    def test_permission_classifier(self):
        self.assertTrue(is_permission_error(354, "not subscribed"))
        self.assertTrue(is_permission_error(162, "No market data permissions"))
        self.assertFalse(is_permission_error(162, "HMDS query returned no data"))
        self.assertFalse(is_permission_error(2104, "market data farm connected"))
        self.assertTrue(is_pacing_error(162, "Historical data request pacing violation"))
        self.assertTrue(is_pacing_error(366, "No historical data query found"))
        self.assertFalse(is_pacing_error(162, "HMDS query returned no data"))
        self.assertEqual(backoff_seconds(1), 15)
        self.assertEqual(backoff_seconds(3), 60)

    def test_pacer_caps_sixty_requests_and_identical_repeats(self):
        pacer = Pacer()
        for i in range(60):
            self.assertEqual(pacer.seconds_until_allowed(f"k{i}", float(i)), 0)
            pacer.mark(f"k{i}", float(i))
        wait = pacer.seconds_until_allowed("new", 60.0)
        self.assertGreater(wait, 500)
        pacer.mark("same", 1000.0)
        self.assertGreaterEqual(pacer.seconds_until_allowed("same", 1005.0), 10)
        self.assertEqual(pacer.seconds_until_allowed("other", 1005.0), 0)

    def test_backfill_skips_saved_days_paces_and_stops_on_permission(self):
        now = datetime(2026, 11, 13, 2, 0, tzinfo=timezone.utc)
        days = closed_session_days(now, 12, use_rth=1)
        self.assertTrue(days)
        self.assertTrue(all(day.weekday() < 5 for day in days))
        self.assertEqual(days[0], datetime(2026, 11, 12).date())
        saved = days[0]

        class Clock:
            def __init__(self):
                self.now = 0.0
                self.sleeps = []

            def __call__(self):
                return self.now

            def sleep(self, seconds):
                self.sleeps.append(seconds)
                self.now += float(seconds)

        class Fake:
            def __init__(self):
                self.kind = 3
                self.calls = []
                self.paced = True

            def set_market_data_type(self, kind):
                self.kind = kind

            def request_day(self, spec, day, use_rth, what):
                self.calls.append((spec["folder"], day, use_rth, what, self.kind))
                out = HistoryOutcome()
                if spec["folder"] == "VIX":
                    out.errors = [{"code": 354, "message": "Requested market data is not subscribed"}]
                    return out
                if spec["folder"] == "VIX1D":
                    out.errors = [{"code": 200, "message": "No security definition has been found"}]
                    return out
                if spec["folder"] == "SPY" and self.paced:
                    self.paced = False
                    out.errors = [{"code": 162, "message": "Historical data request pacing violation"}]
                    return out
                stamp = datetime(day.year, day.month, day.day, 15, 0, tzinfo=timezone.utc)
                out.bars = [_bar(stamp.isoformat(), 100.0)]
                return out

        fake = Fake()
        clock = Clock()
        specs = tuple(spec for spec in IBKR_SPECS if spec["folder"] in {"SPY", "VIX", "VIX1D"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stamp = datetime(saved.year, saved.month, saved.day, 15, 0, tzinfo=timezone.utc)
            store_days(root / "ibkr" / "SPY", [_bar(stamp.isoformat())], now)
            with unittest.mock.patch("archive_1m.IBKR_SPECS", specs):
                report = run_backfill(fake, root, now, backfill_days=12, use_rth=1, clock=clock, max_attempts=3)
            self.assertTrue((root / "ibkr" / "SPY" / f"{saved.isoformat()}.csv.gz").exists())
        self.assertTrue(any(pause >= 15 for pause in clock.sleeps))
        self.assertNotIn(saved, [call[1] for call in fake.calls if call[0] == "SPY"])
        self.assertTrue(all(call[2] == 1 for call in fake.calls))
        self.assertLessEqual(sum(call[0] == "VIX" for call in fake.calls), 4)
        self.assertEqual(sum(call[0] == "VIX1D" for call in fake.calls), 1)
        self.assertIn("VIX", [item["symbol"] for item in report["permission_missing"]])
        self.assertTrue(any(item["symbol"] == "SPY" and item["fetched"] >= 1 for item in report["succeeded"]))


if __name__ == "__main__":
    unittest.main()
