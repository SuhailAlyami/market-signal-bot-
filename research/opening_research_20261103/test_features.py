import unittest
import pandas as pd,numpy as np
from run import features
import early_move_eval_openfix as ev
class OpeningFeatures(unittest.TestCase):
 def frame(self):
  p=100+np.arange(90)*.01
  return ev.add_atr(ev.add_structure(pd.DataFrame({'ts':pd.date_range('2026-10-15T13:30Z',periods=90,freq='min'),'open':p,'high':p+.3,'low':p-.3,'close':p+.05})),'prior20')
 def test_early_finite(self):
  f=features(self.frame());self.assertTrue(f.iloc[:21].isna().all().all());self.assertTrue(np.isfinite(f.iloc[21:60].values).all());self.assertTrue(f.iloc[60:].isna().all().all())
 def test_no_future(self):
  d=self.frame();x=d.copy();x.loc[55:,['open','high','low','close']]*=2
  np.testing.assert_allclose(features(d).iloc[:55],features(x).iloc[:55],equal_nan=True)
 def test_gap_rewarm(self):
  d=self.frame();d.loc[50:,'ts']+=pd.Timedelta(minutes=1);d=ev.add_atr(ev.add_structure(d),'prior20');self.assertTrue(features(d).iloc[50:71].isna().all().all())
if __name__=='__main__':unittest.main()
