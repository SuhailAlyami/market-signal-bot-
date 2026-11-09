import unittest
import pandas as pd
from run import detect
class Tests(unittest.TestCase):
 def data(self):
  c=[100.]*20+[100,98,99,101,103,102,101,100,101,102,104,105,104,103,102,99]
  return pd.DataFrame({'close':c,'atr':1.,'seg':0,'pos':range(len(c))})
 def test_causal_confirmation(self):
  d=self.data();self.assertEqual(detect(d.iloc[:30]),[]);w=detect(d)[0];self.assertEqual(w['i'],30);self.assertEqual(w['last_pivot_confirmed_i'],29)
 def test_no_duplicate(self):self.assertEqual(len(detect(self.data())),1)
 def test_structural_invalidation(self):
  w=detect(self.data())[0];self.assertEqual(w['invalidation'],100);self.assertEqual(w['end'],35)
 def test_mirror(self):
  d=self.data();d.close=200-d.close;self.assertEqual(detect(d)[0]['side'],-1)
 def test_gap_discards_pivots(self):
  d=self.data();d.loc[29:,'seg']=1;d.loc[29:,'pos']=range(7);self.assertEqual(detect(d),[])
if __name__=='__main__':unittest.main()
