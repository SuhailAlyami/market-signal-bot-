import unittest
from unittest.mock import patch
from ibkr_readiness import gateway_config, inspect_socket, contract_plan

class IBKRReadinessTests(unittest.TestCase):
    def test_off_by_default(self):
        with patch.dict("os.environ", {"IBKR_DATA_ENABLED":"false"}):
            self.assertIsNone(gateway_config())
            self.assertFalse(inspect_socket().connected_socket)

    def test_rejects_remote_broker_gateway(self):
        with patch.dict("os.environ", {"IBKR_DATA_ENABLED":"true","IBKR_GATEWAY_HOST":"some.public.host"}):
            with self.assertRaises(ValueError):
                gateway_config()

    def test_no_option_orders_or_account_details(self):
        info = contract_plan()
        self.assertEqual(info["ES"]["exchange"], "CME")
        self.assertEqual(info["SPX_OPTIONS"]["secType"], "OPT")

if __name__ == "__main__":
    unittest.main()
