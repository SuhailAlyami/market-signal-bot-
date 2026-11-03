import unittest,itertools
from audit import distribution,convolve,holm
class Tests(unittest.TestCase):
 def test_matches_enumeration_including_flat(self):
  delta=[1,-1,0,1,-1,1];counts={};total=0
  for long in itertools.combinations(range(6),3):
   ls=set(long);hits=sum((x>0 if i in ls else x<0) for i,x in enumerate(delta));counts[hits]=counts.get(hits,0)+1;total+=1
  d=distribution(delta,3)
  for k,v in counts.items():self.assertAlmostEqual(d[k],v/total)
 def test_degenerate_one_direction(self):self.assertEqual(distribution([1,-1,1],3),{2:1.})
 def test_convolution(self):self.assertEqual(convolve({0:.5,1:.5},{0:.5,1:.5}),{0:.25,1:.5,2:.25})
 def test_holm(self):
  a=holm([.01,.04,.2]);self.assertAlmostEqual(a[0],.03);self.assertAlmostEqual(a[1],.08);self.assertAlmostEqual(a[2],.2)
if __name__=='__main__':unittest.main()
