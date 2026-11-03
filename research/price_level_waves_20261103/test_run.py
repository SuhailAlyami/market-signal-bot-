import unittest
import pandas as pd
from run import detect
class WaveTests(unittest.TestCase):
 def data(self):
  d=pd.DataFrame({'open':[100.]*35,'high':[101.]*35,'low':[99.]*35,'close':[100.]*35,'atr':[1.]*35,'seg':[0]*35,'pos':range(35)})
  d.loc[21:,'close']=[102,103,104,105,104,103,102,101,100,100,100,100,100,100];return d
 def test_confirmation_not_breakout(self):
  r=detect(self.data());self.assertEqual(r[0]['i'],22)
 def test_one_wave(self):self.assertEqual(len(detect(self.data())),1)
 def test_invalidation(self):
  w=detect(self.data())[0];self.assertEqual(w['end_reason'],'STRUCTURE_BREAK');self.assertEqual(w['end'],29)
 def test_gap_clears_state(self):
  d=self.data();d.loc[24:,'seg']=1;d.loc[24:,'pos']=range(11);w=detect(d)[0];self.assertEqual(w['end'],23);self.assertEqual(w['end_reason'],'SESSION_OR_GAP')
 def test_mirror(self):
  d=self.data();d['close']=200-d.close;self.assertEqual(detect(d)[0]['side'],-1)
 def test_prefix(self):
  d=self.data();a=detect(d.iloc[:25])[0];b=detect(d)[0]
  for k in ['i','side','entry','invalidation','origin']:self.assertEqual(a[k],b[k])
if __name__=='__main__':unittest.main()
