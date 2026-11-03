import unittest
import numpy as np,pandas as pd
from run import price_features,volume_features,select
import early_move_eval_openfix as ev
class FeatureChecks(unittest.TestCase):
 def frame(self):
  p=100+np.arange(90)*.01
  return ev.add_atr(ev.add_structure(pd.DataFrame({'ts':pd.date_range('2026-10-15T13:30Z',periods=90,freq='min'),'open':p,'high':p+.2,'low':p-.2,'close':p+.05,'volume':np.arange(1,91,dtype=float)})),'prior20')
 def test_price_warmup(self):
  f=price_features(self.frame());self.assertTrue(f.iloc[:21].isna().all().all());self.assertTrue(np.isfinite(f.iloc[21:].values).all())
 def test_price_future_mutation(self):
  d=self.frame();f=price_features(d);d.loc[60:,['open','high','low','close']]*=2;np.testing.assert_allclose(price_features(d).iloc[:60],f.iloc[:60],equal_nan=True)
 def test_volume_reference_excludes_current(self):
  d=self.frame();a=volume_features(d);d.loc[20,'volume']=10000;b=volume_features(d);self.assertAlmostEqual(21/np.expm1(a.log1p_rvol.iloc[20]),10000/np.expm1(b.log1p_rvol.iloc[20]))
 def test_volume_lag_causal(self):
  d=self.frame();a=volume_features(d);d.loc[30:,'volume']*=100;b=volume_features(d);self.assertEqual(a.log1p_rvol_lag1.iloc[30],b.log1p_rvol_lag1.iloc[30])
 def test_gap_resets_volume(self):
  d=self.frame();d.loc[70:,'ts']+=pd.Timedelta(minutes=1);self.assertTrue(volume_features(d).log1p_rvol.iloc[70:].isna().all())
 def test_select_shared_cooldown(self):
  d=self.frame();p=np.tile([.8,.1],(len(d),1));p[22]=[.1,.9];ids,side=select(d,p,.7,np.arange(len(d))>=21);self.assertEqual(ids[:3].tolist(),[21,31,41]);self.assertEqual(side[:3].tolist(),[1,1,1])
if __name__=='__main__':unittest.main()
