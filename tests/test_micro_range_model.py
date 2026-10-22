import unittest
import pandas as pd
from micro_range_model import candidate,features
from independent_strategy_models import common_risk_plan
from evaluate_micro_range import check_independence,CONSUMED_NATIVE_SHA
from tests.test_hunter_research import minute_bars


class MicroRangeTests(unittest.TestCase):
    def fixture(self):
        return (dict(valid=True,atr=1.,micro_high=101.,micro_low=100.5,rvol=1.5,contraction=.5,
                     trend_5=.3,trend_15=.1,close=101.4),
                pd.Series(dict(Open=100.9,Low=100.8,High=101.5,Close=101.4)))

    def test_local_breakout_without_outer20_band_and_structural_stop(self):
        f,row=self.fixture();found=candidate(f,row)
        self.assertEqual(found['direction'],1);self.assertEqual(found['level'],101.)
        self.assertEqual(found['invalidation'],100.25)
        self.assertIsNotNone(common_risk_plan({'direction':'UP','invalidation':found['invalidation']},f)[0])

    def test_no_lowering_of_volume_trend_and_risk_to_force_signal(self):
        f,row=self.fixture()
        self.assertIsNone(candidate({**f,'rvol':1.19},row))
        self.assertIsNone(candidate({**f,'trend_15':-.1},row))
        rejected=row.copy();rejected.High=102.
        self.assertIsNone(candidate(f,rejected))
        wide=candidate({**f,'micro_low':98.},row)
        self.assertEqual(wide['invalidation'],97.75)
        self.assertIsNone(common_risk_plan({'direction':'UP','invalidation':wide['invalidation']},f)[0])

    def test_future_perturbation_cannot_change_local_levels(self):
        bars=minute_bars(periods=70);before=features(bars).iloc[45]
        bars.iloc[46:,:4]=[999.,1000.,998.,999.]
        pd.testing.assert_series_equal(before,features(bars).iloc[45])

    def test_consumed_sample_cannot_reenter_as_independent(self):
        with self.assertRaisesRegex(ValueError,'consumed'):
            check_independence('independent',dict(input_sha256=CONSUMED_NATIVE_SHA,requested_dates=['2026-09-01']),['2026-07-20'])
        with self.assertRaisesRegex(ValueError,'unregistered'):
            check_independence('independent',dict(input_sha256='new',requested_dates=['2026-09-01']),['2026-07-20'])


if __name__=='__main__':unittest.main()
