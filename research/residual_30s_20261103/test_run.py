import unittest
import pandas as pd
from run import labels,features
class Checks(unittest.TestCase):
 def data(self):
  return pd.DataFrame({'ts':pd.date_range('2026-11-02T15:00Z',periods=12,freq='30s'),'open_SPX':100.,'high_SPX':100.,'low_SPX':100.,'close_SPX':100.,'atr_SPX':1.})
 def result(self,d):return labels(d,[0],[1],'close')[0]['outcome']
 def test_horizon(self):
  d=self.data();d.loc[11,'high_SPX']=102.;self.assertEqual(self.result(d),'TIMEOUT');d.loc[10,'high_SPX']=102.;self.assertEqual(self.result(d),'TARGET')
 def test_open_precedence(self):
  d=self.data();d.loc[1,['open_SPX','high_SPX','low_SPX']]=[102,103,98];self.assertEqual(self.result(d),'TARGET')
 def test_ambiguous(self):
  d=self.data();d.loc[1,['high_SPX','low_SPX']]=[102,99];self.assertEqual(self.result(d),'AMBIGUOUS')
 def test_gap(self):
  d=self.data();d.loc[5:,'ts']+=pd.Timedelta(seconds=30);self.assertEqual(self.result(d),'UNSCORABLE_GAP')
 def test_previous_volume_only(self):
  d=self.data().iloc[[0]*50].reset_index(drop=True);d.ts=pd.date_range('2026-11-02T15:00Z',periods=50,freq='30s');d['close_ES']=100.;d['atr_ES']=1.;d['volume']=10.;d.loc[40,'volume']=100.;f=features(d);self.assertEqual(f.rvol.iloc[40],10.)
if __name__=='__main__':unittest.main()
