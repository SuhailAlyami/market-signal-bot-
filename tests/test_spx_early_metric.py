import unittest
from unittest.mock import patch
from cfd_causal_reference import Bar
from research.spx_early_metric import score
class Tests(unittest.TestCase):
 def calc(self,signals):
  bs=[Bar(i*60000,100,101,99,100) for i in range(80)];ds=[0]*80
  for i,d in signals:ds[i]=d
  with patch('research.spx_early_metric.movement',side_effect=lambda b,t:1 if t==50 else 0):return score(bs,{'test':ds})['models']['test']
 def test_early(self):
  r=self.calc([(47,1)]);self.assertEqual(r['matched'],1);self.assertEqual(r['median_lead_minutes'],3)
 def test_late_not_early(self):self.assertEqual(self.calc([(51,1)])['matched'],0)
 def test_wrong_direction(self):self.assertEqual(self.calc([(49,-1)])['matched'],0)
 def test_duplicate(self):self.assertEqual(self.calc([(47,1),(48,1)])['matched'],1)
if __name__=='__main__':unittest.main()
