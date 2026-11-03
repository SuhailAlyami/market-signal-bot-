import unittest
import pandas as pd
from audit import barriers
class Tests(unittest.TestCase):
 def test_open_precedence(self):self.assertEqual(barriers(pd.DataFrame([{'open':102,'high':103,'low':98}]),100,1,1)[0],'TARGET')
 def test_ambiguous(self):self.assertEqual(barriers(pd.DataFrame([{'open':100,'high':102,'low':99}]),100,1,1)[0],'AMBIGUOUS')
 def test_stop_before_recovery(self):self.assertEqual(barriers(pd.DataFrame([{'open':100,'high':100.5,'low':99},{'open':100,'high':103,'low':100}]),100,1,1)[0],'STOP')
 def test_short_symmetry(self):self.assertEqual(barriers(pd.DataFrame([{'open':100,'high':100.5,'low':98}]),100,1,-1)[0],'TARGET')
if __name__=='__main__':unittest.main()
