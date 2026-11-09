import unittest
from reference_legs import legs
class Tests(unittest.TestCase):
 def test_reversal_known_later(self):
  x=legs([100,105,112,115,110,104,100],10);self.assertEqual(x[0]['start'],0);self.assertEqual(x[0]['end'],3);self.assertEqual(x[0]['confirmed_at'],5)
 def test_small_noise(self):self.assertEqual(legs([100,102,99,101],10),[])
 def test_partial(self):
  x=legs([100,105,112,115],10);self.assertFalse(x[-1]['complete']);self.assertIsNone(x[-1]['confirmed_at'])
if __name__=='__main__':unittest.main()
