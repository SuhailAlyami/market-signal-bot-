import unittest
import numpy as np,pandas as pd
from run import detect
class RuleTests(unittest.TestCase):
 def frame(self):
  d=pd.DataFrame({'open':[100.]*81,'high':[105.]*81,'low':[95.]*81,'close':[100.]*81,'atr':[2.]*81,'seg':[0]*81,'pos':range(81)})
  d.loc[70:79,'high']=100.1;d.loc[70:79,'low']=99.9
  d.loc[80,['open','high','low','close']]=[100.2,100.4,100.2,100.35]
  return d
 def test_detect_small_break(self):self.assertEqual(detect(self.frame())[-1],1)
 def test_reject_large_decision(self):
  d=self.frame();d.loc[80,'high']=104;self.assertEqual(detect(d)[-1],0)
 def test_no_compression(self):
  d=self.frame();d.loc[70:79,'high']=105;d.loc[70:79,'low']=95;self.assertEqual(detect(d)[-1],0)
 def test_gap_warmup(self):
  d=self.frame();d.loc[80,'pos']=0;self.assertEqual(detect(d)[-1],0)
 def test_mirror(self):
  d=self.frame();orig=d.copy();d.open=200-orig.open;d.close=200-orig.close;d.high=200-orig.low;d.low=200-orig.high;self.assertEqual(detect(d)[-1],-1)
if __name__=='__main__':unittest.main()
