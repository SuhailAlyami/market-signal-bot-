from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import pandas as pd

from frozen_day_research import closed_session,check_day_coverage,run


class ForwardDayTests(unittest.TestCase):
    def test_no_fetch_or_results_before_session_closes(self):
        fetch=Mock(side_effect=AssertionError('must not fetch'))
        with tempfile.TemporaryDirectory() as directory:
            report=run(directory,now='2026-10-20T06:00:00Z',fetch=fetch)
            self.assertEqual(report['status'],'WAITING_FOR_CLOSED_SESSION')
            self.assertNotIn('metrics',report)
            self.assertFalse(report['notifications_enabled'])
            fetch.assert_not_called()

    def test_frozen_forward_window_rejects_old_sessions(self):
        self.assertEqual(closed_session('2026-10-19T22:00:00Z')[1],'BEFORE_FROZEN_FORWARD_WINDOW')
        self.assertEqual(closed_session('2026-10-24T22:00:00Z')[1],'NONTRADING_DAY')

    def test_dst_and_early_close_follow_exchange_calendar(self):
        self.assertEqual(closed_session('2026-11-27T18:10:00Z')[1],'WAITING_FOR_CLOSED_SESSION')
        session,status=closed_session('2026-11-27T18:25:00Z')
        self.assertEqual(status,'CLOSED_SESSION')
        self.assertEqual(session.market_close,pd.Timestamp('2026-11-27T18:00:00Z'))

    def test_incomplete_day_and_nonfinite_prices_cannot_be_scored(self):
        session,_=closed_session('2026-10-20T22:00:00Z')
        index=pd.date_range(session.market_open,session.market_close-pd.Timedelta(minutes=1),freq='min')
        data=pd.DataFrame({'Open':10.,'High':11.,'Low':9.,'Close':10.,'Volume':100.},index=index)
        self.assertTrue(check_day_coverage(data,session)[0])
        self.assertFalse(check_day_coverage(data.iloc[:-1],session)[0])
        data.iloc[20,data.columns.get_loc('High')]=float('inf')
        self.assertFalse(check_day_coverage(data,session)[0])

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):closed_session('2026-10-20T22:00:00')
