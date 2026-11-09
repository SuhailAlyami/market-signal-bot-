import unittest,tempfile,io,zipfile
from pathlib import Path
import numpy as np,pandas as pd
from replay import prepare,process
ROOT=Path(__file__).resolve().parent.parent
class ReplayTests(unittest.TestCase):
 def tiny(self):return pd.DataFrame({'timestamp':['2026-10-30T13:30:00Z','2026-10-30T13:31:00Z'],'open':[100,100],'high':[101,101],'low':[99,99],'close':[100,100]})
 def test_forming_removed(self):
  d,a=prepare(self.tiny(),'2026-10-30T13:31:30Z');self.assertEqual(len(d),1);self.assertEqual(a['not_closed'],1)
 def test_reject_naive(self):
  d=self.tiny();d.timestamp=['2026-10-30 13:30:00','2026-10-30 13:31:00']
  with self.assertRaises(ValueError):prepare(d,'2026-10-30T20:00Z')
 def test_reject_duplicate(self):
  d=self.tiny();d.timestamp=d.timestamp.iloc[0]
  with self.assertRaises(ValueError):prepare(d,'2026-10-30T20:00Z')
 def test_reject_bad_ohlc(self):
  d=self.tiny();d.loc[0,'low']=102
  with self.assertRaises(ValueError):prepare(d,'2026-10-30T20:00Z')
 def test_consumed_guard(self):
  with self.assertRaises(ValueError):process('missing.csv','missing.json','2026-10-26T00:00Z','2026-11-02T10:00Z','IBKR_SPX_IND')
 def test_early_close_and_DST(self):
  d=self.tiny();d.timestamp=['2026-11-27T17:59:00Z','2026-11-27T18:00:00Z'];out,a=prepare(d,'2026-11-27T20:00Z');self.assertEqual(len(out),1);self.assertEqual(a['outside_session'],1)
 def test_reproduction_restart_pending(self):
  z=zipfile.ZipFile(ROOT/'FirstRate_SPX_sample.zip');d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d.timestamp=pd.to_datetime(d.timestamp).dt.tz_localize('America/New_York').dt.tz_convert('UTC').astype(str)
  with tempfile.TemporaryDirectory() as td:
   csv=Path(td)/'data.csv';state=Path(td)/'state.json';d.to_csv(csv,index=False)
   args=(csv,state,'2026-10-26T00:00:00Z','2026-11-02T10:00:00Z','FirstRate_SPX_INDEX',True)
   s,a=process(*args);self.assertEqual(len(s['signals']),45);self.assertEqual(sum(x['close_result']=='SUCCESS' for x in s['signals']),12);self.assertEqual(sum(x['close_result']=='FAILURE' for x in s['signals']),32);self.assertEqual(sum(x['close_result']=='UNSCORABLE_GAP' for x in s['signals']),1)
   original=pd.read_csv(Path(__file__).resolve().parent/'reference_signals.csv');self.assertEqual([x['direction'] for x in s['signals']],original.direction.tolist());self.assertEqual(pd.to_datetime([x['decision_utc'] for x in s['signals']],utc=True).tolist(),pd.to_datetime(original.decision_time_Riyadh,utc=True).tolist())
   s2,a2=process(*args);self.assertEqual(a2['new_signals'],0);self.assertEqual(s['signals'],s2['signals'])
 def test_pending_then_resolution(self):
  z=zipfile.ZipFile(ROOT/'FirstRate_SPX_sample.zip');d=pd.read_csv(io.BytesIO(z.read('SPX_1min_sample.csv')));d.timestamp=pd.to_datetime(d.timestamp).dt.tz_localize('America/New_York').dt.tz_convert('UTC').astype(str)
  with tempfile.TemporaryDirectory() as td:
   csv=Path(td)/'data.csv';state=Path(td)/'state.json';d.loc[pd.to_datetime(d.timestamp)<=pd.Timestamp('2026-10-26T14:35:00Z')].to_csv(csv,index=False)
   args=(csv,state,'2026-10-26T00:00:00Z','2026-11-02T10:00:00Z','FirstRate_SPX_INDEX',True)
   s,a=process(*args);self.assertEqual(len(s['signals']),1);self.assertEqual(s['signals'][0]['close_result'],'PENDING');first=s['signals'][0]['id']
   d.to_csv(csv,index=False);s,a=process(*args);self.assertEqual(len(s['signals']),45);self.assertEqual(s['signals'][0]['id'],first);self.assertNotEqual(s['signals'][0]['close_result'],'PENDING')
if __name__=='__main__':unittest.main()
