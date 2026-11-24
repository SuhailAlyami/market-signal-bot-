import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import first_hour as F
from daily_range import NY, DataUnavailable


def at(h, mi, day=(2026, 11, 24)):
    return datetime(*day, h, mi, tzinfo=NY).astimezone(timezone.utc)


class FirstHourTests(unittest.TestCase):
    def test_levels_and_tiers(self):
        lv = F.levels(7010, 6990, 7000, 100)
        self.assertAlmostEqual(lv['up'][0], 7010+28.9)
        self.assertAlmostEqual(lv['dn'][1], 6990-73.6)
        self.assertEqual(lv['big_tier'], 0)                      # range 0.2 m: small first hour
        self.assertEqual(F.levels(7030, 6990, 7000, 100)['big_tier'], 1)
        self.assertEqual(F.levels(7050, 6990, 7000, 100)['big_tier'], 2)

    def test_message_has_levels_odds_and_source(self):
        lv = F.levels(7050, 6990, 7020, 100)
        text = F.message(at(10, 30).astimezone(NY).date(), lv, at(10, 30).astimezone(NY))
        for s in ('7,050', '6,990', '7,079', '75%', '95%', 'مرتفع', '29%', 'Yahoo', '10:30'):
            self.assertIn(s, text)

    def test_window_and_holiday(self):
        with mock.patch.object(F.CAL, 'is_session', return_value=False):
            self.assertIsNone(F.build(now=at(10, 45)))
        with mock.patch.object(F.CAL, 'is_session', return_value=True):
            self.assertEqual(F.build(now=at(9, 50)), 'EARLY')
            self.assertEqual(F.build(now=at(13, 0)), 'LATE')

    def test_build_uses_complete_first_hour(self):
        t0 = at(9, 30).astimezone(NY)
        bars = [(t0+timedelta(minutes=5*i), 7000+i, 6990-i, 6995+i) for i in range(12)]
        with mock.patch.object(F.CAL, 'is_session', return_value=True), \
             mock.patch.object(F, 'first_hour_bars', return_value=bars), \
             mock.patch.object(F, 'last_close', side_effect=[(None, 7000.0), (None, 16.0)]):
            text = F.build(now=at(10, 40))
        self.assertIn('7,011', text)          # first-hour high
        self.assertIn('6,979', text)          # first-hour low
        self.assertIn('10:30 نيويورك', text)

    def test_incomplete_hour_fails_closed(self):
        r = {'timestamp': [int(at(9, 30).timestamp())], 'indicators': {'quote': [{'high': [1], 'low': [1], 'close': [1]}]}}
        with mock.patch.object(F, 'yahoo_chart', return_value=r):
            with self.assertRaises(DataUnavailable):
                F.first_hour_bars(at(9, 30).astimezone(NY).date())


if __name__ == '__main__':
    unittest.main()
