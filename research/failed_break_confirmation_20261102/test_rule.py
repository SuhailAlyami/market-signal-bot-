import unittest
import pandas as pd,numpy as np
from run import detect
class TestRule(unittest.TestCase):
 def frame(self):
  d=pd.DataFrame({'open':[100.]*33,'high':[101.]*33,'low':[99.]*33,'close':[100.]*33,'atr':[2.]*33,'pos':range(33)})
  d.loc[31,['open','high','low','close']]=[99.5,100,98.7,99.6]
  d.loc[32,['open','high','low','close']]=[99.7,100.7,99.5,100.5]
  return d
 def test_confirmation_only(self):
  d=self.frame();self.assertEqual(detect(d)[31],0);self.assertEqual(detect(d)[32],1)
 def test_no_confirmation(self):
  d=self.frame();d.loc[32,'close']=99.9;self.assertEqual(detect(d)[32],0)
 def test_gap_resets_history(self):
  d=self.frame();d.loc[32,'pos']=1;self.assertEqual(detect(d)[32],0)
 def test_mirror(self):
  d=self.frame();orig=d.copy();d['open']=200-orig.open;d['close']=200-orig.close;d['high']=200-orig.low;d['low']=200-orig.high;self.assertEqual(detect(d)[32],-1)
if __name__=='__main__':unittest.main()
