import unittest
import pandas as pd
from failure_audit import outcome
class AuditTests(unittest.TestCase):
 def test_open_first(self):self.assertEqual(outcome(pd.DataFrame([{'open':102,'high':103,'low':98}]),100,1,1),'TARGET')
 def test_ambiguity(self):self.assertEqual(outcome(pd.DataFrame([{'open':100,'high':102,'low':99}]),100,1,1),'AMBIGUOUS')
 def test_stop_then_target(self):self.assertEqual(outcome(pd.DataFrame([{'open':100,'high':101,'low':99},{'open':100,'high':103,'low':100}]),100,1,1),'STOP')
 def test_timeout(self):self.assertEqual(outcome(pd.DataFrame([{'open':100,'high':101,'low':99.5}]),100,1,1),'TIMEOUT')
if __name__=='__main__':unittest.main()
