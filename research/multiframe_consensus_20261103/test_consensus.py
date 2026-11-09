import unittest
import pandas as pd
from consensus import asof_direction
class Tests(unittest.TestCase):
 def test_future_excluded(self):
  d=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T15:02Z'],utc=True)});h=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T15:00Z','2026-11-02T15:15Z'],utc=True),'direction':[1,-1]});self.assertEqual(asof_direction(d,h).direction.iloc[0],1)
 def test_exact_close_available(self):
  t=pd.to_datetime(['2026-11-02T15:00Z'],utc=True);self.assertEqual(asof_direction(pd.DataFrame({'available':t}),pd.DataFrame({'available':t,'direction':[1]})).direction.iloc[0],1)
 def test_invalid_current_blocks_stale(self):
  d=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T15:16Z'],utc=True)});h=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T15:00Z','2026-11-02T15:15Z'],utc=True),'direction':[1,0]});self.assertEqual(asof_direction(d,h).direction.iloc[0],0)
 def test_no_previous_is_missing(self):
  d=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T14:00Z'],utc=True)});h=pd.DataFrame({'available':pd.to_datetime(['2026-11-02T15:00Z'],utc=True),'direction':[1]});self.assertTrue(pd.isna(asof_direction(d,h).direction.iloc[0]))
if __name__=='__main__':unittest.main()
