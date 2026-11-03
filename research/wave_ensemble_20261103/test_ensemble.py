import unittest
import pandas as pd
from ensemble import combine
class Tests(unittest.TestCase):
 def d(self):return pd.DataFrame({'ts':pd.date_range('2026-10-26T14:00Z',periods=40,freq='min'),'seg':0,'atr':1.})
 def w(self,i=1,side=1):return {'i':i,'side':side,'end':35,'end_reason':'DATA_END'}
 def test_related_not_two_votes(self):self.assertEqual(combine(self.d(),{'early':[self.w()],'confirmed':[self.w()]},'agreement'),[])
 def test_independent_families(self):self.assertEqual(len(combine(self.d(),{'level':[self.w()],'early':[self.w()]},'agreement')),1)
 def test_same_time_duplicate(self):self.assertEqual(len(combine(self.d(),{'level':[self.w()],'early':[self.w()]},'union')),1)
 def test_conflict(self):self.assertEqual(combine(self.d(),{'level':[self.w()],'early':[self.w(side=-1)]},'union'),[])
 def test_cooldown(self):self.assertEqual(len(combine(self.d(),{'early':[self.w(1),self.w(2),self.w(11)]},'union')),2)
if __name__=='__main__':unittest.main()
