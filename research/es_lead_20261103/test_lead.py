import unittest
import numpy as np,pandas as pd
from run import inputs
class ESLeadChecks(unittest.TestCase):
 def pair(self):
  ts=pd.date_range('2026-10-15T13:30Z',periods=33,freq='min')
  sp=pd.DataFrame({'ts':ts,'open':100.,'high':100.2,'low':99.8,'close':100.})
  es=sp.copy();es['volume']=100.;es.loc[31,['open','high','low','close','volume']]=[100,102,99.9,101.9,200];es.loc[32,['open','high','low','close']]=[101.9,102,101.8,101.9]
  return sp,es
 def test_es_can_trigger_without_spx(self):
  sp,es=self.pair();_,s,v=inputs(sp,es);self.assertTrue(v[31]);self.assertEqual(s['ES_lead_same_close'][31],1);self.assertEqual(s['SPX_ACCEl_baseline'][31],0)
 def test_no_volume_confirmation(self):
  sp,es=self.pair();es.loc[31,'volume']=100;_,s,v=inputs(sp,es);self.assertEqual(s['ES_lead_same_close'][31],0)
 def test_spx_already_confirmed_blocks(self):
  sp,es=self.pair();sp.loc[31,['open','high','low','close']]=[100,102,99.9,101.9];_,s,v=inputs(sp,es);self.assertEqual(s['ES_lead_same_close'][31],0)
 def test_lag_uses_previous_only(self):
  sp,es=self.pair();_,s,v=inputs(sp,es);self.assertEqual(s['ES_lead_lag1'][31],0);self.assertEqual(s['ES_lead_lag1'][32],1)
 def test_future_prefix(self):
  sp,es=self.pair();_,a,_=inputs(sp,es);_,b,_=inputs(sp.iloc[:32],es.iloc[:32]);np.testing.assert_array_equal(a['ES_lead_same_close'][:32],b['ES_lead_same_close'])
if __name__=='__main__':unittest.main()
