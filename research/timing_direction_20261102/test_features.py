import unittest
import numpy as np,pandas as pd
from run import features
import early_move_eval_openfix as ev
class Checks(unittest.TestCase):
 def frame(self):
  t=pd.date_range('2026-10-15 13:30',periods=100,freq='min',tz='UTC');p=100+np.arange(100)*.02
  return ev.add_atr(ev.add_structure(pd.DataFrame({'ts':t,'open':p,'high':p+.2,'low':p-.2,'close':p+.05})),'prior20')
 def test_future_mutation(self):
  d=self.frame();e=d.copy();e.loc[80:,['open','high','low','close']]*=2
  np.testing.assert_allclose(features(d).iloc[:80],features(e).iloc[:80],equal_nan=True)
 def test_warmup(self):self.assertTrue(features(self.frame()).iloc[:60].isna().all().all())
 def test_gap_reset(self):
  d=self.frame().drop(columns=['seg','pos','gap_s'],errors='ignore');d.loc[80:,'ts']+=pd.Timedelta(minutes=1)
  d=ev.add_atr(ev.add_structure(d),'prior20');self.assertTrue(features(d).iloc[80:].isna().all().all())
if __name__=='__main__':unittest.main()
