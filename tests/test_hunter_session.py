import tempfile
import unittest
from unittest.mock import Mock
import pandas as pd

from hunter_session import collector_lock,cycle,run_loop


class SessionTests(unittest.TestCase):
    def test_closed_and_premarket_do_not_fetch_or_authorize(self):
        for now,status in [('2026-10-20T07:00:00Z','WAITING_FOR_NY_OPEN'),
                           ('2026-10-20T20:00:00Z','NY_CLOSED'),
                           ('2026-10-24T14:00:00Z','NONTRADING_DAY')]:
            fetch=Mock(side_effect=AssertionError('no request'))
            auth=Mock(side_effect=AssertionError('no auth'))
            with tempfile.TemporaryDirectory() as directory:
                report=cycle(directory,now=now,fetch=fetch,auth=auth)
            self.assertEqual(report['status'],status)
            fetch.assert_not_called();auth.assert_not_called()

    def test_missing_authorization_stops_without_provider_fallback(self):
        fetch=Mock()
        with tempfile.TemporaryDirectory() as directory:
            r=cycle(directory,now='2026-10-20T14:00:00Z',fetch=fetch,
                    auth=lambda:{'status':'AUTHORIZATION_REQUIRED','runtime_auth_present':False})
        self.assertEqual(r['status'],'AUTHORIZATION_REQUIRED')
        fetch.assert_not_called()

    def test_two_detectors_share_only_one_request_per_symbol(self):
        frame=pd.DataFrame({'Close':[10.]})
        frame.attrs={'source':'IBKR MCP','live_feed_verified':True}
        fetch=Mock(return_value=frame)
        def canonical(f):
            f('ES=F');f('NQ=F')
            return {'heartbeat':{'status':'ok'}}
        def ny(f):
            f('ES');f('NQ')
            return {'status':'NY_OPEN','new_candidates':[]}
        with tempfile.TemporaryDirectory() as directory:
            r=cycle(directory,now='2026-10-20T14:00:00Z',fetch=fetch,
                    auth=lambda:{'status':'AUTH_PRESENT_UNVERIFIED','runtime_auth_present':True},
                    canonical=canonical,ny=ny)
        self.assertEqual(r['status'],'OBSERVED')
        self.assertEqual([c.args[0] for c in fetch.call_args_list],['ES','NQ'])
        self.assertFalse(r['notifications_enabled'])
        self.assertFalse(r['orders_enabled'])

    def test_provider_error_is_shared_and_not_retried_by_second_detector(self):
        fetch=Mock(side_effect=ValueError('unavailable'))
        def canonical(f):
            try:f('ES=F')
            except ValueError:pass
            return {'heartbeat':{'status':'degraded'}}
        def ny(f):
            try:f('ES')
            except ValueError:pass
            return {'status':'DATA_UNAVAILABLE'}
        with tempfile.TemporaryDirectory() as directory:
            r=cycle(directory,now='2026-10-20T14:00:00Z',fetch=fetch,
                    auth=lambda:{'status':'AUTH_PRESENT_UNVERIFIED','runtime_auth_present':True},
                    canonical=canonical,ny=ny)
        self.assertEqual(r['status'],'DATA_UNAVAILABLE')
        self.assertEqual(fetch.call_count,1)

    def test_polling_cadence_deducts_network_time_and_stops_at_close(self):
        t=[0.];starts=[]
        def tick():
            starts.append(t[0]);t[0]+=17
            return {'status':'OBSERVED' if len(starts)<3 else 'NY_CLOSED'}
        def sleep(n):t[0]+=n
        result=run_loop('.',tick=tick,monotonic=lambda:t[0],sleep=sleep,max_hours=1)
        self.assertEqual(starts,[0.,60.,120.])
        self.assertEqual(result['status'],'NY_CLOSED')

    def test_collector_lock_prevents_double_launch_and_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            with collector_lock(directory):
                with self.assertRaises(RuntimeError):
                    with collector_lock(directory):pass
            with collector_lock(directory):pass

    def test_runtime_auth_expiry_stops_the_collector(self):
        with tempfile.TemporaryDirectory() as directory:
            r=cycle(directory,now='2026-10-20T14:00:00Z',
                    auth=lambda:{'status':'AUTH_PRESENT_UNVERIFIED','runtime_auth_present':True},
                    canonical=lambda f:{'heartbeat':{'status':'degraded','symbols':{'ES':{'data_status':'renew_runtime_authorization'}}}},
                    ny=lambda f:{'status':'DATA_UNAVAILABLE'})
        self.assertEqual(r['status'],'AUTHORIZATION_REQUIRED')

    def test_rejects_unbounded_runtime_or_subminute_polling(self):
        for kwargs in ({'interval':30},{'max_hours':0},{'max_hours':25}):
            with self.assertRaises(ValueError):run_loop('.',**kwargs)
