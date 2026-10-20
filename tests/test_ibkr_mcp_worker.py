from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import ibkr_mcp_worker as worker


class WorkerTests(unittest.TestCase):
    def test_disabled_worker_never_starts(self):
        with patch.dict(os.environ, {"IBKR_MCP_ENABLED": "false"}):
            with patch("threading.Thread") as thread:
                self.assertIsNone(worker.start_worker())
                thread.assert_not_called()
            self.assertEqual(worker.get_status()["status"], "disabled")

    def test_authorization_required_saved_without_enabling_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            report = {"status": "authorization_required", "readiness": "NOT_READY", "orders_enabled": False,
                      "observed_at": datetime.now(timezone.utc).isoformat(), "reason": "authorize_runtime_separately"}
            with patch.dict(os.environ, {"IBKR_MCP_ENABLED": "true", "IBKR_MCP_REPORT": str(path)}):
                with patch("ibkr_mcp_client.run_collection", new=AsyncMock(return_value=report)) as collect:
                    self.assertEqual(worker.poll_once(), report)
                    collect.assert_awaited_once_with(authorize=False)
                self.assertEqual(worker.get_status()["status"], "authorization_required")
                self.assertEqual(json.loads(path.read_text()), report)

    def test_exception_becomes_redacted_error_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            with patch.dict(os.environ, {"IBKR_MCP_REPORT": str(path)}):
                with patch("ibkr_mcp_client.run_collection", new=AsyncMock(side_effect=RuntimeError("private token"))):
                    report = worker.poll_once()
            self.assertEqual(report["status"], "error")
            self.assertFalse(report["orders_enabled"])
            self.assertNotIn("private token", path.read_text())

    def test_existing_worker_not_duplicated(self):
        with patch.dict(os.environ, {"IBKR_MCP_ENABLED": "true"}):
            with patch.object(worker, "_THREAD") as thread:
                thread.is_alive.return_value = True
                self.assertIs(worker.start_worker(), thread)
