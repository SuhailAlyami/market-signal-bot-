"""HTTP liveness must expose detector/data health without implying prediction success."""
import unittest
from unittest.mock import patch

import market_signal_bot as app_module


class HunterAppTests(unittest.TestCase):
    def test_shadow_boot_does_not_require_telegram_or_contact_provider(self):
        with patch.object(app_module, "TELEGRAM_TOKEN", ""), patch.object(
            app_module, "AdvancedSignalDatabase"
        ) as database, patch("requests.sessions.Session.request") as network:
            database.return_value.load_adaptive_weights.return_value = {}
            bot = app_module.EvolutionaryTradingBot()
            self.assertIsNone(bot.bot)
            self.assertTrue(bot.is_running)
            network.assert_not_called()

    def test_health_exposes_stale_feed_separately_from_http_liveness(self):
        snapshot = {"status": "degraded", "alerts_enabled": False,
                    "symbols": {"ES=F": {"status": "stale_feed", "last_completed_bar": "2026-10-19T08:52:00+00:00"}}}
        with patch("globex_render_worker.get_status", return_value=snapshot):
            response = app_module.app.test_client().get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["process"], "alive")
        self.assertEqual(response.json["prediction_readiness"], "NOT READY")
        self.assertEqual(response.json["hunter"], snapshot)
        self.assertNotIn("healthy", response.json.values())


if __name__ == "__main__":
    unittest.main()
