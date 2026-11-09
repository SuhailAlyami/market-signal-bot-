import unittest
import pandas as pd
from run import detect
class Checks(unittest.TestCase):
 def data(self):
  d=pd.DataFrame({'open':[99.5]*30,'high':[100.]*30,'low':[99.]*30,'close':[99.5]*30,'atr':[1.]*30,'seg':[0]*30,'pos':range(30)})
  d.loc[21,['open','high','low','close']]=[99.8,100.4,99.8,100.3]
  d.loc[22,['open','high','low','close']]=[100.,100.3,99.9,100.2]
  return d
 def test_wait_retest(self):
  s=detect(self.data());self.assertEqual(s[21],0);self.assertEqual(s[22],1)
 def test_invalidation(self):
  d=self.data();d.loc[22,['low','close']]=[99.6,99.7];self.assertEqual(detect(d)[22],0)
 def test_gap(self):
  d=self.data();d.loc[22:,'seg']=1;d.loc[22:,'pos']=range(8);self.assertEqual(detect(d)[22],0)
 def test_short_mirror(self):
  d=self.data();c=d.copy();c['open']=200-d.open;c['close']=200-d.close;c['high']=200-d.low;c['low']=200-d.high;self.assertEqual(detect(c)[22],-1)
if __name__=='__main__':unittest.main()
