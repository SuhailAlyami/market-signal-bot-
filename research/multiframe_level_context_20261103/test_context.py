import unittest
import pandas as pd,numpy as np
from context_audit import context
class Tests(unittest.TestCase):
 def data(self):return pd.DataFrame({'ts':pd.date_range('2026-10-26T14:00Z',periods=15,freq='min'),'seg':0,'close':[100.]*5+[102.]*5+[99.]*5})
 def test_available_at_close(self):
  x=context(self.data());self.assertEqual(x[8],0);self.assertEqual(x[9],1);self.assertEqual(x[14],-1)
 def test_no_future(self):
  d=self.data();x=context(d);d.loc[10:,'close']=500;self.assertTrue(np.array_equal(x[:10],context(d)[:10]))
 def test_incomplete(self):self.assertEqual(context(self.data().iloc[:3]).tolist(),[0,0,0])
 def test_gap_reset(self):
  d=self.data();d.loc[5:,'seg']=1;self.assertEqual(context(d)[9],0)
if __name__=='__main__':unittest.main()
