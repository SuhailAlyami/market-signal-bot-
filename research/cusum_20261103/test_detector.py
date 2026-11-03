import unittest
import pandas as pd,numpy as np
from run import detect
class CusumTests(unittest.TestCase):
 def frame(self):
  p=np.r_[np.ones(22)*100,100.7,101.4,102.1,np.ones(15)*102.1]
  return pd.DataFrame({'ts':pd.date_range('2026-10-15T13:30Z',periods=len(p),freq='min'),'close':p,'atr':np.ones(len(p)),'pos':range(len(p)),'seg':np.ones(len(p),int)})
 def test_accumulates(self):
  d=self.frame();s=detect(d);self.assertEqual(s[24],1);self.assertEqual(np.count_nonzero(s[:24]),0)
 def test_mirror(self):
  d=self.frame();a=detect(d);d.close=200-d.close;np.testing.assert_array_equal(detect(d),-a)
 def test_no_motion(self):
  d=self.frame();d.close=100;self.assertEqual(np.count_nonzero(detect(d)),0)
 def test_gap_resets(self):
  d=self.frame();d.loc[24:,'seg']=2;d.loc[24:,'pos']=range(len(d)-24);self.assertEqual(np.count_nonzero(detect(d)),0)
 def test_no_future(self):
  d=self.frame();np.testing.assert_array_equal(detect(d.iloc[:25]),detect(d)[:25])
if __name__=='__main__':unittest.main()
