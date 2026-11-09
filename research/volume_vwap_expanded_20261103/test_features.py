import unittest
import pandas as pd,numpy as np
from run import es_features
class VWAPChecks(unittest.TestCase):
 def frame(self):
  p=np.arange(100,125,dtype=float);return pd.DataFrame({'ts':pd.date_range('2026-10-15T13:30Z',periods=25,freq='min'),'open':p,'high':p+1,'low':p-1,'close':p,'volume':np.ones(25)})
 def test_weighted_proxy(self):
  d=self.frame().iloc[:2].copy();d.loc[1,['open','high','low','close']]=[110,111,109,110];d.loc[1,'volume']=3;f=es_features(d);self.assertEqual(f.vwap.iloc[1],107.5)
 def test_missing_open_invalid(self):self.assertFalse(es_features(self.frame().iloc[1:]).anchor_complete.any())
 def test_gap_invalidates_rest(self):
  d=self.frame().drop(index=10).reset_index(drop=True);f=es_features(d);self.assertTrue(f.anchor_complete.iloc[:10].all());self.assertFalse(f.anchor_complete.iloc[10:].any())
 def test_future_mutation(self):
  d=self.frame();a=es_features(d);d.loc[20:,'volume']*=100;d.loc[20:,'close']*=2;b=es_features(d);np.testing.assert_allclose(a[['rvol','vwap','vwap_prior5']].iloc[:20],b[['rvol','vwap','vwap_prior5']].iloc[:20],equal_nan=True)
 def test_next_day_reset(self):
  d=self.frame();other=d.iloc[:2].copy();other.ts+=pd.Timedelta(days=1);other.loc[:,'close']=200;other.loc[:,'high']=201;other.loc[:,'low']=199;f=es_features(pd.concat([d,other],ignore_index=True));self.assertEqual(f.vwap.iloc[25],200);self.assertTrue(np.isnan(f.rvol.iloc[25]))
if __name__=='__main__':unittest.main()
