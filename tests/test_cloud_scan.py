import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import cloud_scan


class CloudShadowTests(unittest.TestCase):
    def run_status(self, status):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Mock(state_path=Path(directory) / "state.json")
            result = {"heartbeat": {"status": status, "alerts_enabled": False}, "events": []}
            with patch.object(cloud_scan, "create_runtime", return_value=runtime), patch.object(
                cloud_scan, "run_once", return_value=result
            ) as poll, patch("requests.sessions.Session.request") as outbound:
                code = cloud_scan.run(state_dir=directory)
                poll.assert_called_once()
                outbound.assert_not_called()
            saved = json.loads((Path(directory) / "heartbeat.json").read_text())
            self.assertEqual(saved, result["heartbeat"])
            return code

    def test_healthy_shadow_needs_no_notification_credentials(self):
        self.assertEqual(self.run_status("ok"), 0)

    def test_data_outage_is_observable_and_fails_workflow(self):
        self.assertEqual(self.run_status("degraded"), 1)


if __name__ == "__main__":
    unittest.main()
