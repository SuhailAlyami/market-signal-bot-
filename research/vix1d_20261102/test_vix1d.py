import unittest
import numpy as np,pandas as pd
from run_vix1d import vix_feature
class Tests(unittest.TestCase):
 def frame(self):return pd.DataFrame({'ts':pd.date_range('2026-01-01',periods=15,freq='min',tz='UTC'),'close':np.arange(15,dtype=float)+10})
 def test_six_bars_required(self):
  d=self.frame();x=vix_feature(d,d);self.assertTrue(np.isnan(x[:5]).all());self.assertEqual(x[5],5)
 def test_missing_timestamp_not_filled(self):
  d=self.frame();v=d.drop(index=8);x=vix_feature(d,v);self.assertTrue(np.isnan(x[8]));self.assertTrue(np.isnan(x[9]))
 def test_lag_defers_feature(self):
  d=self.frame();x=vix_feature(d,d,1);self.assertTrue(np.isnan(x[5]));self.assertEqual(x[6],5)
 def test_future_change_no_past_effect(self):
  d=self.frame();v=d.copy();v.loc[10:,'close']+=100;self.assertTrue(np.allclose(vix_feature(d,d)[:10],vix_feature(d,v)[:10],equal_nan=True))
if __name__=='__main__':unittest.main()
