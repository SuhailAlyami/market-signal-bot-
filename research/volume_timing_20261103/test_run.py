import unittest
import pandas as pd,numpy as np
from run import timing,r
class Tests(unittest.TestCase):
 def data(self):
  d=pd.DataFrame({'ts':pd.date_range('2026-10-26T14:00Z',periods=40,freq='min'),'open':100.,'high':100.5,'low':99.5,'close':100.})
  d=r.ev.add_structure(d);d['atr']=1.;return d
 def test_either_direction_ignores_stop(self):
  d=self.data();d.loc[22,['high','low']]=[102,98];y,ok=timing(d);self.assertTrue(ok[21]);self.assertTrue(y[21])
 def test_horizon(self):
  d=self.data();d.loc[27,'high']=102.;y,ok=timing(d);self.assertFalse(y[21]);self.assertTrue(y[22])
 def test_gap(self):
  d=self.data();d.loc[22:,'ts']+=pd.Timedelta(minutes=1);d=r.ev.add_structure(d);y,ok=timing(d);self.assertFalse(ok[21])
 def test_features_prefix(self):
  d=r.ev.add_atr(self.data(),'prior20');full=r.price_features(d);np.testing.assert_allclose(r.price_features(d.iloc[:30]),full.iloc[:30],equal_nan=True)
if __name__=='__main__':unittest.main()
