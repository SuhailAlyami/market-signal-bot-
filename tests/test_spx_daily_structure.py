import unittest
from test_spx_daily import fixture
from spx_daily import features, forecast, VERSION, BASELINE_VERSION

class StructureTests(unittest.TestCase):
    def test_causal_features_and_forecast(self):
        rows=fixture(); a=features(rows[:90])[1]; full=features(rows)[1]
        self.assertTrue(a.equals(full.iloc[:90]))
        p=forecast(rows[:90]); rows[-1]['high']=90000
        self.assertEqual(p,forecast(rows[:90]))
    def test_failed_break_is_distinct(self):
        rows=fixture();rows[-1].update(open=5080,high=5200,low=5070,close=5090)
        x=features(rows)[1]
        self.assertEqual(x.iloc[-1].failed_high,1)
        self.assertEqual(x.iloc[-1].failed_low,0)
        self.assertGreater(x.iloc[-1].upper_rejection,0)
    def test_baseline_remains_separate(self):
        rows=fixture()
        self.assertEqual(len(features(rows,False)[1].columns),6)
        self.assertEqual(forecast(rows,False)['model_version'],BASELINE_VERSION)
        self.assertEqual(forecast(rows)['model_version'],VERSION)
        self.assertIsNone(forecast(rows)['confidence'])
