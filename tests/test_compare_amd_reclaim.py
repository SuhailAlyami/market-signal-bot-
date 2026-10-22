import unittest
import pandas as pd

from compare_amd_reclaim import amd_candidate, baseline_candidate, rolling_features, improvement_gate
from strategy_rules import candidate, features
from tests.test_hunter_research import minute_bars


class ComparisonTests(unittest.TestCase):
    def test_cached_baseline_matches_production_prefix_and_future_is_irrelevant(self):
        bars=minute_bars(periods=90)
        cached=rolling_features(bars)
        for i in (30,45,65,89):
            actual=features(bars.iloc[:i+1],i)
            for key in ('atr','range_high','range_low','rvol','trend_5','trend_15','near_high','near_low'):
                self.assertAlmostEqual(float(cached.iloc[i][key]),float(actual[key]))
            self.assertEqual(baseline_candidate(cached.iloc[i]),candidate(bars.iloc[:i+1],i))
        original=amd_candidate(cached.iloc[45],bars.iloc[45])
        bars.iloc[46:,:4]=[999.,1000.,998.,999.]
        after=rolling_features(bars)
        self.assertEqual(amd_candidate(after.iloc[45],bars.iloc[45]),original)
        pd.testing.assert_series_equal(cached.iloc[45],after.iloc[45])

    def test_strict_reclaim_both_sides_and_actual_wick_stop(self):
        f=dict(valid=True,contraction=.5,rvol=1.5,range_low=99.,range_high=101.,atr=2.)
        row=pd.Series(dict(Open=99.,Close=100.,Low=98.75,High=100.5))
        found=amd_candidate(f,row)
        self.assertEqual(found['direction'],1);self.assertEqual(found['invalidation'],98.5)
        self.assertIsNone(amd_candidate(f,row.copy().set_axis(row.index).where(row.index!='Close',99.)))
        row.High=102.
        self.assertIsNone(amd_candidate(f,row))

    def test_comparison_cannot_select_empty_or_faster_but_less_precise_model(self):
        base=dict(sessions=5,signals=30,early_precision=.2,early_event_recall=.1,
                  precision=.5,false_alarms_per_session=3.,median_lead_minutes=0.)
        self.assertTrue(improvement_gate(base,{**base,'early_event_recall':.2,'median_lead_minutes':1.}))
        self.assertFalse(improvement_gate(base,{**base,'early_event_recall':.2,'precision':.4,'median_lead_minutes':1.}))
        self.assertFalse(improvement_gate(base,{**base,'signals':0,'early_event_recall':.2}))


if __name__=='__main__':unittest.main()
