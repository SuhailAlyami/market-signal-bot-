import unittest
import pandas as pd,numpy as np
from run import prepare,ft
class FrameTests(unittest.TestCase):
 def data(self,ts):
  n=len(ts);return pd.DataFrame({'ts':pd.to_datetime(ts,utc=True),'open':100.,'high':101.,'low':99.,'close':100.,'volume':10.})
 def test_overnight_trading_history(self):
  sp=self.data(['2026-11-02T20:45Z','2026-11-03T14:30Z']);d,e=prepare(sp,sp,15);self.assertEqual(d.seg.iloc[0],d.seg.iloc[1]);self.assertEqual(d.pos.iloc[1],1)
 def test_missing_bar_resets(self):
  sp=self.data(['2026-11-02T14:30Z','2026-11-02T15:00Z']);d,e=prepare(sp,sp,15);self.assertNotEqual(d.seg.iloc[0],d.seg.iloc[1])
 def test_dst_available_time(self):
  sp=self.data(['2026-11-02T14:30Z']);d,e=prepare(sp,sp,15);self.assertEqual(str(d.available.iloc[0].tz_convert('Asia/Riyadh')),'2026-11-02 17:45:00+03:00')
 def test_daily_weekend(self):
  sp=self.data(['2026-10-30T13:30Z','2026-11-02T14:30Z']);d,e=prepare(sp,sp,None);self.assertEqual(d.seg.iloc[0],d.seg.iloc[1]);self.assertEqual(d.available.iloc[1],pd.Timestamp('2026-11-02T21:00Z'))
 def test_reject_after_nyse_close(self):
  sp=self.data(['2026-11-02T21:00Z']);d,e=prepare(sp,sp,30);self.assertEqual(len(d),0)
if __name__=='__main__':unittest.main()
