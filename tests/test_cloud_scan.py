import unittest
from datetime import datetime, timezone
from unittest.mock import Mock, patch
import cloud_scan

ITEM = {"symbol": "ES=F", "direction": "WATCH_DOWN", "bar_end": "2026-10-19T00:15:00+00:00",
        "price": 6500.5, "top": 6510.0, "bottom": 6504.0, "rvol": 1.8}
NOW = datetime(2026, 10, 19, 0, 30, tzinfo=timezone.utc)

class CloudAlertTests(unittest.TestCase):
    def test_issue_contains_identity_timestamp_and_nontrade_warning(self):
        title, body = cloud_scan.issue_payload(ITEM, "ASIA", NOW)
        self.assertIn("ES=F WATCH_DOWN", title)
        self.assertIn("live_feed_verified", body)
        self.assertIn("not a trade recommendation", body)
        self.assertIn("2026-10-19T00:15:00", body)

    @patch.object(cloud_scan, "TOKEN", "fake")
    @patch.object(cloud_scan, "REPO", "owner/repo")
    def test_existing_issue_deduplicated(self):
        title, _ = cloud_scan.issue_payload(ITEM, "ASIA", NOW)
        resp = Mock()
        resp.json.return_value = {"items": [{"title": title}]}
        session = Mock()
        session.get.return_value = resp
        self.assertFalse(cloud_scan.publish_issue(ITEM, "ASIA", NOW, session))
        session.post.assert_not_called()

    @patch.object(cloud_scan, "TOKEN", "fake")
    @patch.object(cloud_scan, "REPO", "owner/repo")
    def test_missing_signal_produces_no_issue(self):
        with patch.object(cloud_scan, "asia_session", return_value=True), patch.object(
            cloud_scan, "market_session_open", return_value=False), patch.object(
            cloud_scan, "scan_once", return_value=[]):
            self.assertEqual(cloud_scan.run(NOW), 0)

    def test_no_credentials_fails_closed(self):
        with patch.object(cloud_scan, "TOKEN", ""), patch.object(cloud_scan, "REPO", "owner/repo"):
            self.assertEqual(cloud_scan.run(NOW), 1)

if __name__ == "__main__":
    unittest.main()
