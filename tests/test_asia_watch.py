import unittest
from datetime import datetime, timezone
import pandas as pd
from asia_watch import detect, asia_session, futures_session_start

class AsiaWatchTests(unittest.TestCase):
    def test_asia_gate(self):
        self.assertTrue(asia_session(datetime(2026,10,19,2,0,tzinfo=timezone.utc)))
        self.assertFalse(asia_session(datetime(2026,10,18,2,0,tzinfo=timezone.utc)))
        self.assertFalse(asia_session(datetime(2026,10,19,14,0,tzinfo=timezone.utc)))
        # Sunday evening US is already Monday morning Tokyo: watch from Globex open.
        self.assertTrue(asia_session(datetime(2026,10,18,22,0,tzinfo=timezone.utc)))
        self.assertFalse(asia_session(datetime(2026,10,18,21,59,tzinfo=timezone.utc)))
        self.assertEqual(futures_session_start(datetime(2026,10,18,22,5,tzinfo=timezone.utc)).hour,22)
        # US winter DST transition moves Globex reopen to 23:00 UTC.
        self.assertTrue(asia_session(datetime(2026,11,1,23,5,tzinfo=timezone.utc)))
        self.assertFalse(asia_session(datetime(2026,11,1,22,59,tzinfo=timezone.utc)))
    def test_fresh_confirmed_opening_range_breakout(self):
        now=datetime(2026,10,19,2,30,tzinfo=timezone.utc)
        idx=pd.date_range("2026-10-18T21:00:00Z",periods=22,freq="15min")
        bars=pd.DataFrame({"High":[101.0]*22,"Low":[99.0]*22,
            "Close":[100.0]*22,"Volume":[100.0]*22},index=idx)
        # Latest completed bar starts 02:00 UTC (last bar is 02:15 uncompleted at 02:30? 02:15 is completed).
        bars.loc[idx[-1],"Low"]=97
        bars.loc[idx[-1],"Close"]=98
        bars.loc[idx[-1],"Volume"]=300
        result=detect("ES=F",bars,now)
        self.assertIsNotNone(result)
        self.assertEqual(result["direction"],"WATCH_DOWN")
    def test_stale_bars_rejected(self):
        idx=pd.date_range("2026-10-18T20:00:00Z",periods=24,freq="15min")
        bars=pd.DataFrame({"High":[101.0]*24,"Low":[99.0]*24,
            "Close":[98.0]*24,"Volume":[300.0]*24},index=idx)
        self.assertIsNone(detect("ES=F",bars,datetime(2026,10,19,5,tzinfo=timezone.utc)))

if __name__=="__main__":
    unittest.main()
