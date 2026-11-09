import unittest
import numpy as np
from walkforward import folds,training_mask
class Tests(unittest.TestCase):
 def test_no_repeated_test_rows(self):
  fs=list(folds(986));rows=[i for _,a,b in fs for i in range(a,b)];self.assertEqual(len(rows),len(set(rows)));self.assertEqual(rows[0],400);self.assertEqual(rows[-1],985)
 def test_purge_horizon(self):
  n=500;mask=training_mask(n,6,300,np.ones(n,bool),np.ones(n,bool),np.ones(n));self.assertTrue(mask[293]);self.assertFalse(mask[294]);self.assertFalse(mask[400])
 def test_future_target_changes_do_not_change_fit_rows(self):
  n=500;delta=np.ones(n);args=(n,6,300,np.ones(n,bool),np.ones(n,bool));a=training_mask(*args,delta);delta[300:]=0;self.assertTrue(np.array_equal(a,training_mask(*args,delta)))
if __name__=='__main__':unittest.main()
