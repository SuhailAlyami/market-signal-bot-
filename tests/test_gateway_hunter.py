import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from gateway_hunter import DataClient, send_test, reader_lock


class GatewayTests(unittest.TestCase):
    def test_only_one_reader_owns_state(self):
        with tempfile.TemporaryDirectory() as directory:
            with reader_lock(directory):
                with self.assertRaises(OSError):
                    with reader_lock(directory): pass
            with reader_lock(directory): pass

    def client(self):
        c = DataClient()
        c.isConnected = lambda: True
        c.kind = 1; c.trade_time = 1000; c.received = 1000
        c.rows = {960: [10, 12, 9, 11, 50]}
        return c

    def test_realtime_fresh_frame(self):
        c = self.client()
        frame = c.frame('ES=F', now=1002)
        self.assertTrue(frame.attrs['live_feed_verified'])
        self.assertEqual(str(frame.index.tz), 'UTC')
        self.assertEqual(frame.iloc[0].Volume, 50)

    def test_fail_closed_on_delayed_stale_disconnected_and_future(self):
        for attr, value, now in [('kind', 3, 1001), ('trade_time', 900, 1001),
                                  ('received', 900, 1001), ('lost', True, 1001),
                                  ('trade_time', 1010, 1001)]:
            with self.subTest(attr=attr, value=value):
                c = self.client(); setattr(c, attr, value)
                with self.assertRaises(RuntimeError): c.frame('ES', now)

    def test_connectivity_loss_invalidates_feed(self):
        c = self.client(); c.error(-1, 1100, 'Connection lost')
        with self.assertRaises(RuntimeError): c.frame('ES', 1001)
        self.assertEqual(c.errors[0]['code'], 1100)

    def test_orders_always_blocked(self):
        with self.assertRaises(PermissionError): self.client().placeOrder(1, None, None)

    def test_telegram_missing_credentials_and_persisted_dedupe(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            with patch.dict('os.environ', {}, clear=True):
                self.assertEqual(send_test(directory, {})['status'], 'credentials_unavailable')
            (directory/'telegram-test.json').write_text(json.dumps({'message_id': 123}), encoding='utf-8')
            with patch('gateway_hunter.urllib.request.urlopen') as request:
                self.assertEqual(send_test(directory, {})['message_id'], 123)
                request.assert_not_called()

    def test_telegram_receipt_and_label(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict('os.environ', {'TELEGRAM_BOT_TOKEN':'test', 'TELEGRAM_CHAT_ID':'test'}):
                with patch('gateway_hunter.urllib.request.urlopen') as request:
                    request.return_value.__enter__.return_value.read.return_value = b'{"ok":true,"result":{"message_id":42}}'
                    receipt = send_test(Path(folder), {'tick_count': 3})
                    self.assertEqual(receipt['message_id'], 42)
                    self.assertFalse(receipt['human_read_verified'])
                    from urllib.parse import parse_qs
                    data = parse_qs(request.call_args.args[0].data.decode())
                    self.assertIn('اختبار فقط', data['text'][0])


if __name__ == '__main__': unittest.main()
