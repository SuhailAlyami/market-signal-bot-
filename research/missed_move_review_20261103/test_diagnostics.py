import unittest
from analyze import legs
class DiagnosticTests(unittest.TestCase):
 def test_turns(self):
  x=legs([100,112,125,114,105,116]);self.assertEqual([(z['start'],z['end'],z['direction']) for z in x],[(0,2,1),(2,4,-1),(4,5,1)]);self.assertFalse(x[-1]['complete'])
 def test_mirror(self):
  p=[100,112,125,114,105,116];a=legs(p);b=legs([200-x for x in p]);self.assertEqual([(x['start'],x['end']) for x in a],[(x['start'],x['end']) for x in b]);self.assertEqual([x['direction'] for x in a],[-x['direction'] for x in b])
 def test_small_oscillations(self):self.assertEqual(legs([100,102,99,101]),[])
if __name__=='__main__':unittest.main()
