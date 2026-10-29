import asyncio
import unittest

import pandas as pd

from ibkr_market_data import IBKRDataUnavailable, collect_history


NOW = pd.Timestamp('2026-10-29T14:00:00Z')


class TradeMetadataTests(unittest.TestCase):
    def provider(self, trade=None, status='REALTIME'):
        async def call(name, args):
            if name == 'search_contracts':
                return {'results': [{'symbol': 'SPX', 'country_code': 'US',
                        'exchange': 'CBOE', 'underlying_contract_id': 416904,
                        'sections': [{'security_type': 'IND'}]}]}
            if name == 'get_price_snapshot':
                return {'top-status': {'status': status},
                        'last': {'price': 7000.5, 'ts': trade}}
            if name == 'get_price_history':
                return {'time': [(NOW-pd.Timedelta(minutes=1)).isoformat()],
                        'open': [7000.], 'high': [7001.], 'low': [6999.],
                        'close': [7000.], 'volume': [0.]}
            raise AssertionError(name)
        return call

    def test_provider_trade_time_survives_history_collection(self):
        trade = NOW-pd.Timedelta(seconds=2)
        data = asyncio.run(collect_history(self.provider(trade.timestamp()),
                          'SPX', now=NOW, step_count=1))
        self.assertEqual(data.attrs['last_trade_time'], trade.isoformat())
        self.assertEqual(data.attrs['last_price'], 7000.5)
        self.assertEqual(data.attrs['observed_at'], NOW.isoformat())
        self.assertNotEqual(data.attrs['last_trade_time'], data.attrs['observed_at'])
        self.assertTrue(data.attrs['live_feed_verified'])

    def test_missing_stale_future_or_unverified_time_is_not_replaced(self):
        for trade, status in ((None, 'REALTIME'),
                              ((NOW-pd.Timedelta(seconds=61)).timestamp(), 'REALTIME'),
                              ((NOW+pd.Timedelta(seconds=1)).timestamp(), 'REALTIME'),
                              (NOW.timestamp(), 'FROZEN'),
                              (NOW.timestamp(), 'DELAYED')):
            with self.subTest(trade=trade, status=status):
                with self.assertRaises(IBKRDataUnavailable):
                    asyncio.run(collect_history(self.provider(trade, status),
                                'SPX', now=NOW, step_count=1))
        historical = asyncio.run(collect_history(self.provider(), 'SPX',
                     now=NOW, step_count=1, require_realtime=False))
        self.assertNotIn('last_trade_time', historical.attrs)
        self.assertNotIn('last_price', historical.attrs)
        self.assertFalse(historical.attrs['live_feed_verified'])


if __name__ == '__main__':
    unittest.main()
