import ast
from pathlib import Path
import tempfile
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from spx_price_watch import candidate, observe, market_open


def frame():
    data = pd.DataFrame({'Open': [100.]*35, 'High': [100.2]*35,
                         'Low': [99.8]*35, 'Close': [100.]*35},
                        index=pd.date_range('2026-10-22T14:00Z', periods=35, freq='min'))
    data.attrs.update(symbol='SPX', security_type='IND', source='IBKR Gateway TWS API',
                      live_feed_verified=True)
    return data


class PriceWatchTests(unittest.TestCase):
    def test_downward_local_break_inside_twenty_bar_range_is_observed(self):
        data = frame(); data.iloc[15] = [100, 100.2, 95, 100]
        data.iloc[30] = [100, 100.1, 98.9, 99]
        result = candidate(data, 30)
        self.assertEqual(result['direction'], -1)
        self.assertEqual(result['kind'], 'LOCAL_BREAK')
        self.assertEqual(result['level'], 99.8)
        self.assertIsNone(result['rvol'])
        self.assertGreater(result['price'], 95)  # Still within old 20-bar range.

    def test_large_direct_break_is_not_rejected_for_point_three_atr_overshoot(self):
        data = frame(); data.iloc[30] = [100, 100.1, 96.9, 97]
        self.assertEqual(candidate(data, 30)['direction'], -1)

    def test_failed_upside_sweep_reclaims_inside_without_fifteen_bar_downtrend(self):
        data = frame(); data.iloc[30] = [100.15, 101, 99.95, 100.05]
        result = candidate(data, 30)
        self.assertEqual((result['direction'], result['kind']), (-1, 'SWEEP_RECLAIM'))
        self.assertEqual(result['invalidation'], 101)

    def test_failed_downside_sweep_is_symmetric(self):
        data = frame(); data.iloc[30] = [99.85, 100.05, 99, 99.95]
        result = candidate(data, 30)
        self.assertEqual((result['direction'], result['kind']), (1, 'SWEEP_RECLAIM'))
        self.assertEqual(result['invalidation'], 99)

    def test_two_sided_sweep_is_rejected(self):
        data = frame(); data.iloc[30] = [100, 101, 99, 100.1]
        self.assertEqual(observe(data, 30)['reason'], 'ambiguous_two_sided_sweep')

    def test_future_rows_cannot_change_a_prior_decision(self):
        data = frame(); data.iloc[30] = [100, 100.1, 98.9, 99]
        result = observe(data, 30)
        data.iloc[31:] = [1, 100000, .01, 50000]
        self.assertEqual(observe(data, 30), result)

    def test_no_volume_companion_or_dataframe_mutation(self):
        data = frame(); data.iloc[30] = [100, 100.1, 98.9, 99]
        before = data.copy(deep=True); result = observe(data, 30)
        data['Volume'] = float('nan')
        self.assertEqual(observe(data, 30), result)
        assert_frame_equal(data.drop(columns='Volume'), before)
        self.assertFalse(result['volume_used'])
        self.assertIsNone(result['support_symbol'])
        self.assertFalse(result['notify_eligible'])

    def test_invalid_ohlc_gap_and_non_spx_are_rejected(self):
        for case in ('nan', 'ohlc', 'gap', 'naive', 'SPX500'):
            data = frame()
            if case == 'nan': data.iloc[30, 3] = float('nan')
            elif case == 'ohlc': data.iloc[30, 1] = 90
            elif case == 'gap': data.index = data.index.where(data.index != data.index[29], data.index[29]-pd.Timedelta(seconds=30))
            elif case == 'naive': data.index = data.index.tz_localize(None)
            else: data.attrs['symbol'] = 'SPX500'
            self.assertIsNone(candidate(data, 30), case)

    def test_no_setup_when_no_price_condition(self):
        self.assertIsNone(candidate(frame(), 30))

    def test_calendar_regular_holiday_early_close_and_dst(self):
        for stamp, expected in [('2026-10-22T13:29Z', False), ('2026-10-22T13:30Z', True),
                                ('2026-10-22T20:00Z', False), ('2026-12-25T15:00Z', False),
                                ('2026-11-27T17:59Z', True), ('2026-11-27T18:00Z', False),
                                ('2026-11-02T14:29Z', False), ('2026-11-02T14:30Z', True)]:
            self.assertEqual(market_open(pd.Timestamp(stamp).to_pydatetime()), expected, stamp)

    def test_primary_no_longer_calls_es_or_option_senders(self):
        tree = ast.parse((Path(__file__).resolve().parents[1]/'spx_primary.py').read_text())
        run = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run')
        called = [n.func.id for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
        self.assertNotIn('es_fetch', called)
        self.assertNotIn('supporting_frame', called)
        self.assertNotIn('complete_plan', called)
        self.assertNotIn('option_candidate', called)
        self.assertNotIn('deliver', called)
        self.assertNotIn('telegram_deliver', called)


if __name__ == '__main__':
    unittest.main()
