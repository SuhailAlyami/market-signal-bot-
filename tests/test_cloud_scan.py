import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cloud_scan


class CloudShadowTests(unittest.TestCase):
    def run_status(self, status, symbols=None, allow_stale_feed=False):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Mock(state_path=Path(directory) / "state.json")
            result = {"heartbeat": {"status": status, "alerts_enabled": False}, "events": []}
            if symbols is not None:
                result["heartbeat"]["symbols"] = symbols
            with patch.object(cloud_scan, "create_runtime", return_value=runtime), patch.object(
                cloud_scan, "run_once", return_value=result
            ) as poll, patch("requests.sessions.Session.request") as outbound:
                code = cloud_scan.run(state_dir=directory, allow_stale_feed=allow_stale_feed)
                poll.assert_called_once()
                outbound.assert_not_called()
            saved = json.loads((Path(directory) / "heartbeat.json").read_text())
            self.assertEqual(saved, result["heartbeat"])
            return code

    def test_healthy_shadow_needs_no_notification_credentials(self):
        self.assertEqual(self.run_status("ok"), 0)

    def test_data_outage_is_observable_and_fails_workflow(self):
        self.assertEqual(self.run_status("degraded"), 1)

    def test_scheduled_stale_feed_is_recorded_without_job_failure(self):
        self.assertEqual(self.run_status("degraded", {
            "ES=F": {"status": "stale_feed"}, "NQ=F": {"status": "closed"}
        }, allow_stale_feed=True), 0)

    def test_strict_mode_still_fails_stale_feed(self):
        self.assertEqual(self.run_status("degraded", {
            "ES=F": {"status": "stale_feed"}
        }), 1)

    def test_real_errors_are_not_suppressed(self):
        for status in ("provider_error", "detector_error", "unavailable", "unknown"):
            with self.subTest(status=status):
                self.assertEqual(self.run_status("degraded", {
                    "ES=F": {"status": "stale_feed"}, "NQ=F": {"status": status}
                }, allow_stale_feed=True), 1)
        for status in ("persistence_failed", "calendar_unavailable"):
            self.assertEqual(self.run_status(status, {
                "ES=F": {"status": "stale_feed"}
            }, allow_stale_feed=True), 1)

    def test_missing_details_remain_fatal(self):
        self.assertEqual(self.run_status("degraded", allow_stale_feed=True), 1)

    def test_recovery_gap_remains_fatal(self):
        self.assertEqual(self.run_status("degraded", {
            "ES=F": {"status": "stale_feed"},
            "NQ=F": {"status": "ok", "recovery_status": "missed_polling_bars"}
        }, allow_stale_feed=True), 1)

    def test_summary_keeps_degraded_health_visible(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = Path(directory) / "summary.md"
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary)}):
                self.assertEqual(self.run_status("degraded", {
                    "ES=F": {"status": "stale_feed"}
                }, allow_stale_feed=True), 0)
            text = summary.read_text()
            self.assertIn('"status": "degraded"', text)
            self.assertIn('"alerts_enabled": false', text)
            self.assertIn("not live-feed verification", text)


if __name__ == "__main__":
    unittest.main()

