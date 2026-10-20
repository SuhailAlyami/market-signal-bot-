import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

from ny_intraday_shadow import observe, run, session_at


def fixture():
    index = pd.date_range('2026-10-20T12:30:00Z', periods=80, freq='min')
    data = pd.DataFrame({'Open':100., 'High':101., 'Low':99., 'Close':100., 'Volume':100.}, index=index)
    return {'ES':data.copy(), 'NQ':data.copy()}


def configs():
    return {sym:{'fixture':('fixture',{},lambda row,method,params: 1)} for sym in ('ES','NQ')}


class NYShadowTests(unittest.TestCase):
    def test_calendar_open_close_dst_and_holiday(self):
        session,status = session_at('2026-10-20T13:00:00Z')
        self.assertEqual(status,'WAITING_FOR_NY_OPEN')
        self.assertEqual(session.market_open.tz_convert('Asia/Riyadh').hour,16)
        self.assertEqual(session_at('2026-10-20T13:30:00Z')[1],'NY_OPEN')
        self.assertEqual(session_at('2026-10-20T20:00:00Z')[1],'NY_CLOSED')
        self.assertEqual(session_at('2026-11-27T18:00:00Z')[1],'NY_CLOSED')
        self.assertEqual(session_at('2026-10-24T14:00:00Z')[1],'NONTRADING_DAY')
        self.assertEqual(session_at('2026-11-02T14:00:00Z')[1],'WAITING_FOR_NY_OPEN')

    def test_closed_gate_does_not_fetch_or_load_models(self):
        fetch=Mock(side_effect=AssertionError('no fetch'))
        with tempfile.TemporaryDirectory() as directory:
            result=run(directory,now='2026-10-20T07:00:00Z',fetch=fetch)
        fetch.assert_not_called()
        self.assertEqual(result['status'],'WAITING_FOR_NY_OPEN')
        self.assertFalse(result['notifications_enabled'])

    def test_actual_receipt_prevents_retroactive_early_credit_and_duplicates(self):
        frames=fixture();state={}
        session,_=session_at('2026-10-20T13:50:00Z')
        records=observe(frames,configs(),state,'2026-10-20T13:50:00Z',session)
        self.assertEqual(len(records),4)
        self.assertTrue(all(r['timing_status']=='LATE' for r in records))
        self.assertTrue(all(r['detected_at']=='2026-10-20T13:50:00+00:00' for r in records))
        self.assertEqual(observe(frames,configs(),state,'2026-10-20T13:55:00Z',session),[])
        self.assertTrue(all(not r['feed_realtime_verified'] for r in records))

    def test_incomplete_and_future_bars_not_archived(self):
        frames=fixture();state={}
        session,_=session_at('2026-10-20T13:32:30Z')
        observe(frames,configs(),state,'2026-10-20T13:32:30Z',session)
        self.assertEqual(max(pd.Timestamp(k) for k in state['bars']['ES']),pd.Timestamp('2026-10-20T13:31:00Z'))

    def test_first_seen_values_survive_provider_revisions(self):
        frames=fixture();state={}
        session,_=session_at('2026-10-20T13:40:00Z')
        observe(frames,configs(),state,'2026-10-20T13:40:00Z',session)
        key='2026-10-20T13:30:00+00:00'
        original=state['bars']['ES'][key].copy()
        frames['ES'].loc[pd.Timestamp(key),'Close']=100.5
        observe(frames,configs(),state,'2026-10-20T13:45:00Z',session)
        self.assertEqual(state['bars']['ES'][key],original)

    def test_late_counterpart_uses_later_receipt(self):
        frames=fixture();state={}
        session,_=session_at('2026-10-20T13:40:00Z')
        full=frames['NQ'].copy()
        frames['NQ']=full.loc[full.index<pd.Timestamp('2026-10-20T13:30:00Z')]
        self.assertEqual(observe(frames,configs(),state,'2026-10-20T13:40:00Z',session),[])
        frames['NQ']=full
        records=observe(frames,configs(),state,'2026-10-20T13:45:00Z',session)
        self.assertTrue(all(r['detected_at']=='2026-10-20T13:45:00+00:00' for r in records))

    def test_naive_clock_rejected(self):
        with self.assertRaises(ValueError):session_at('2026-10-20T13:40:00')
