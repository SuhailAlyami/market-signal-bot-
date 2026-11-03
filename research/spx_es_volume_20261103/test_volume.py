import unittest
import pandas as pd,numpy as np
from run import volume_features
class VolumeChecks(unittest.TestCase):
 def frame(self):return pd.DataFrame({'ts':pd.date_range('2026-11-02T14:30Z',periods=30,freq='min'),'volume':np.arange(1,31,dtype=float)})
 def test_reference_excludes_current(self):
  d=self.frame();a=volume_features(d);d.loc[20,'volume']=10000;b=volume_features(d);self.assertEqual(21/a.rvol.iloc[20],10000/b.rvol.iloc[20]);self.assertEqual(21/a.rvol.iloc[20],10.5)
 def test_zero_reference_rejected(self):
  d=self.frame();d.loc[:19,'volume']=0;self.assertTrue(np.isnan(volume_features(d).rvol.iloc[20]))
 def test_gap_resets(self):
  d=self.frame();d.loc[22:,'ts']+=pd.Timedelta(minutes=1);x=volume_features(d);self.assertTrue(x.rvol.iloc[22:].isna().all())
 def test_lag_does_not_use_current(self):
  d=self.frame();a=volume_features(d);d.loc[25,'volume']=10000;b=volume_features(d);self.assertEqual(a.rvol_lag1.iloc[25],b.rvol_lag1.iloc[25]);self.assertEqual(a.rvol_lag1.iloc[25],a.rvol.iloc[24])
 def test_prefix_invariant(self):
  d=self.frame();a=volume_features(d);b=volume_features(d.iloc[:25]);np.testing.assert_allclose(a.rvol.iloc[:25],b.rvol,equal_nan=True)
 def test_duplicate_rejected(self):
  d=self.frame();d.loc[2,'ts']=d.ts.iloc[1]
  with self.assertRaises(ValueError):volume_features(d)
if __name__=='__main__':unittest.main()
