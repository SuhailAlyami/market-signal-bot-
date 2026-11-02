import unittest
from run_options_direction import option_side
class Tests(unittest.TestCase):
 def test_long_short_symmetry(self):
  self.assertEqual(option_side(10,11,10,9,[1,1,1,1],True),1)
  self.assertEqual(option_side(10,9,10,11,[1,1,1,1],True),-1)
 def test_zero_volume_rejected(self):self.assertEqual(option_side(10,11,10,9,[1,0,1,1],True),0)
 def test_gap_rejected(self):self.assertEqual(option_side(10,11,10,9,[1,1,1,1],False),0)
 def test_same_direction_no_signal(self):self.assertEqual(option_side(10,11,10,11,[1,1,1,1],True),0)
if __name__=='__main__':unittest.main()
