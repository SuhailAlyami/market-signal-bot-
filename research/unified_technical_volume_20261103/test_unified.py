import unittest
import numpy as np,pandas as pd
from features import technical,patterns
from train import select
import early_move_eval_openfix as ev
class Tests(unittest.TestCase):
 def data(self):
  c=100+np.arange(100)*.02+np.sin(np.arange(100)/3)
  d=pd.DataFrame({'ts':pd.date_range('2026-10-26T14:00Z',periods=100,freq='min'),'open':c-.1,'high':c+.5,'low':c-.5,'close':c});d=ev.add_atr(ev.add_structure(d),'prior20');es=d.copy();es['volume']=10.;return d,es
 def test_channel_excludes_current(self):
  d,es=self.data();f=technical(d,es);d.loc[80,'high']+=50;g=technical(d,es);self.assertEqual(f.channel_width20.iloc[80],g.channel_width20.iloc[80])
 def test_volume_baseline_previous_only(self):
  d,es=self.data();es.loc[80,'volume']=100;self.assertAlmostEqual(technical(d,es).log_rvol.iloc[80],np.log1p(10))
 def test_source_models_count_and_prefix(self):
  d,es=self.data();a=patterns(d);self.assertEqual(a.shape,(100,18));np.testing.assert_array_equal(patterns(d.iloc[:80]),a.iloc[:80])
 def test_cooldown(self):
  d,es=self.data();ids,side=select(d,np.ones(100,bool),np.ones(100,int),np.ones(100,bool));self.assertTrue((np.diff(ids)>=10).all())
 def test_features_prefix(self):
  d,es=self.data();np.testing.assert_allclose(technical(d.iloc[:80],es),technical(d,es).iloc[:80],equal_nan=True)
if __name__=='__main__':unittest.main()
