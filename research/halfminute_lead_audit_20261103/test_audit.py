import unittest
import numpy as np,pandas as pd
from audit import minute_bars,pairs
class AuditTests(unittest.TestCase):
 def test_minute_reconstruction(self):
  d=pd.DataFrame({'ts':pd.date_range('2026-11-02T14:30Z',periods=2,freq='30s'),'open':[100,102],'high':[104,105],'low':[99,101],'close':[102,103]});a=minute_bars(d);self.assertEqual(a[['open','high','low','close']].iloc[0].tolist(),[100,105,99,103])
 def test_missing_half_rejected(self):
  d=pd.DataFrame({'ts':[pd.Timestamp('2026-11-02T14:30Z')],'open':[100],'high':[101],'low':[99],'close':[100]});self.assertEqual(len(minute_bars(d)),0)
 def frame(self):
  return pd.DataFrame({'ts':pd.date_range('2026-11-02T14:30Z',periods=8,freq='30s'),'close_ES':[100,101,103,104,107,108,112,113],'close_SPX':[200,203,204,207,210,211,212,216]})
 def test_positive_lag_means_future_spx(self):
  d=self.frame();x,y,ok=pairs(d,1);self.assertAlmostEqual(x[0],np.log(101/100));self.assertAlmostEqual(y[0],np.log(204/203))
 def test_no_cross_gap_pairs(self):
  d=self.frame();d.loc[4:,'ts']+=pd.Timedelta(seconds=30);_,_,ok=pairs(d,1);self.assertFalse(ok.iloc[3]);self.assertFalse(ok.iloc[4])
if __name__=='__main__':unittest.main()
