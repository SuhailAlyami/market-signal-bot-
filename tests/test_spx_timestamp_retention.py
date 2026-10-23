from datetime import datetime, timedelta, timezone
import threading
import unittest

from gateway_spx_probe import Probe
from spx_primary import index_frame


class TimestampRetentionTests(unittest.TestCase):
    def client(self, now):
        # Exercise the real callbacks without connecting to TWS.
        client = Probe()
        client.isConnected = lambda: True
        client.types[201] = 1
        client.lost = False
        client.lock = threading.Lock()
        start = int((now - timedelta(minutes=32)).timestamp())
        client.rows = {start + i*60: [7000., 7001., 6999., 7000.]
                       for i in range(32)}
        return client

    def prices(self, client):
        for i in range(200):
            client.tickPrice(201, 4, 7000. + i/100, None)

    def test_missing_old_or_delayed_trade_time_stays_rejected(self):
        now = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
        for kind, offset, reason in ((None, 0, 'timestamp_missing'),
                                     (45, 11, 'spx_index_stale'),
                                     (88, 1, 'timestamp_missing')):
            with self.subTest(kind=kind, offset=offset):
                client = self.client(now)
                if kind is not None:
                    client.tickString(201, kind, str(int((now-timedelta(seconds=offset)).timestamp())))
                self.prices(client)
                with self.assertRaisesRegex(RuntimeError, reason):
                    index_frame(client, now)

    def test_real_recent_trade_time_survives_quote_log_churn(self):
        now = datetime(2026, 10, 22, 15, tzinfo=timezone.utc)
        client = self.client(now)
        trade = now-timedelta(seconds=2)
        client.tickString(201, 45, str(int(trade.timestamp())))
        original_receipt = client.quotes[201][0]['received_at']
        self.prices(client)
        frame = index_frame(client, now)
        self.assertEqual(frame.attrs['last_trade_time'], trade.isoformat())
        self.assertEqual(frame.attrs['observed_at'], now.isoformat())
        self.assertNotEqual(frame.attrs['last_trade_time'], original_receipt)
        self.assertLessEqual(len(client.quotes[201]), 150)
        retained = [q for q in client.quotes[201] if q['type']==45]
        self.assertEqual(retained[-1]['received_at'], original_receipt)
        # A newly received price never refreshes the retained trade time.
        with self.assertRaisesRegex(RuntimeError, 'spx_index_stale'):
            index_frame(client, now+timedelta(seconds=9))


if __name__ == '__main__':
    unittest.main()
