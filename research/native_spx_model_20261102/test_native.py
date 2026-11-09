import unittest
import numpy as np,pandas as pd
from run_native import features,select,ev
class NativeTests(unittest.TestCase):
 def data(self):
  c=100+np.arange(100)*.01;d=pd.DataFrame({'ts':pd.date_range('2026-01-01',periods=100,freq='min',tz='UTC'),'open':c,'high':c+.2,'low':c-.2,'close':c});return ev.EV.add_atr(ev.EV.add_structure(d),'prior20')
 def test_future_does_not_change_features(self):
  d=self.data();a=features(d);b=d.copy();b.loc[80:,'close']+=100;self.assertTrue(np.allclose(features(b).iloc[:80],a.iloc[:80],equal_nan=True))
 def test_past_sixty_ranges_required(self):
  f=features(self.data());self.assertTrue(f.iloc[:60].ATR20_to_prior60TR.isna().all());self.assertTrue(np.isfinite(f.iloc[60].ATR20_to_prior60TR))
 def test_low_score_does_not_consume_cooldown(self):
  d=self.data();p=np.zeros((100,2));p[0]=[.1,0];p[1]=[.3,0];p[11]=[0,.3];i,s=select(d,p,.2,np.ones(100,bool));self.assertEqual(i.tolist(),[1,11])
if __name__=='__main__':unittest.main()
