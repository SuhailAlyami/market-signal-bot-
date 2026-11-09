import unittest
import pandas as pd
from audit import evaluate
class Tests(unittest.TestCase):
 def data(self):return pd.DataFrame({'ts':pd.date_range('2026-10-26T14:00Z',periods=40,freq='min'),'close':[100.]*30+[105.]*10,'seg':0})
 def test_endpoint_not_temporary(self):
  d=self.data();d.loc[5,'close']=120;rows,n=evaluate(d,[{'i':0,'side':1,'atr':2}]);self.assertEqual(rows[0]['signed_delta_points'],5)
 def test_short_mirror(self):
  rows,n=evaluate(self.data(),[{'i':0,'side':-1,'atr':2}]);self.assertFalse(rows[0]['direction_correct']);self.assertEqual(rows[0]['signed_delta_points'],-5)
 def test_gap_excluded(self):
  d=self.data();d.loc[20:,'seg']=1;rows,n=evaluate(d,[{'i':0,'side':1,'atr':2}]);self.assertEqual(n,1);self.assertEqual(rows,[])
 def test_flat_not_hit(self):
  d=self.data();d.close=100.;rows,n=evaluate(d,[{'i':0,'side':1,'atr':2}]);self.assertTrue(rows[0]['flat']);self.assertFalse(rows[0]['direction_correct'])
if __name__=='__main__':unittest.main()
