import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from ibkr_feed_preflight import main as preflight_main
from session_health import inspect
from hunter_session import run_loop

NOW=datetime(2026,10,20,14,tzinfo=timezone.utc)

class HealthTests(unittest.TestCase):
    def check(self, payload, now=NOW):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'heartbeat.json'
            if payload is not None:p.write_text(json.dumps(payload))
            return inspect(p,now=now)

    def good(self):
        return {'status':'OBSERVED','checked_at':NOW.isoformat(),
                'canonical_heartbeat':{'status':'ok'},'frozen_status':'NY_OPEN'}

    def test_missing_invalid_stale_future_never_ready(self):
        for payload in [None, {}, {'checked_at':None},
                        {**self.good(),'checked_at':NOW.replace(tzinfo=None).isoformat()},
                        {**self.good(),'checked_at':(NOW-timedelta(seconds=181)).isoformat()},
                        {**self.good(),'checked_at':(NOW+timedelta(seconds=1)).isoformat()}]:
            with self.subTest(payload=payload):
                self.assertFalse(self.check(payload)['collector_running_verified'])

    def test_observed_cannot_be_inferred_from_auth_or_ci_alone(self):
        for status in ('AUTH_PRESENT_UNVERIFIED','WAITING_FOR_NY_OPEN','RUNTIME_ERROR','DATA_UNAVAILABLE'):
            self.assertFalse(self.check({**self.good(),'status':status})['collector_running_verified'])
        self.assertFalse(self.check({'status':'OBSERVED','checked_at':NOW.isoformat()})['collector_running_verified'])

    def test_successful_cycle_is_not_detector_quality_proof(self):
        result=self.check(self.good())
        self.assertTrue(result['collector_running_verified'])
        self.assertEqual(result['detector_quality'],'NOT_READY')
        self.assertFalse(result['orders_enabled'])

    def test_closed_and_early_close_sessions_never_mark_active(self):
        for now in (datetime(2026,10,20,10,tzinfo=timezone.utc),
                    datetime(2026,11,27,18,1,tzinfo=timezone.utc)):
            self.assertFalse(self.check({**self.good(),'checked_at':now.isoformat()},now)['collector_running_verified'])

    def test_tick_exception_persists_sanitized_failure_and_next_cycle_recovers(self):
        t=[0.];calls=[0]
        with tempfile.TemporaryDirectory() as d:
            def tick():
                calls[0]+=1
                if calls[0]==1:raise RuntimeError('PRIVATE_TOKEN_DO_NOT_EXPORT')
                failure=json.loads((Path(d)/'session-heartbeat.json').read_text())
                self.assertEqual(failure['status'],'RUNTIME_ERROR')
                self.assertNotIn('PRIVATE_TOKEN',json.dumps(failure))
                return {'status':'NY_CLOSED'}
            result=run_loop(d,tick=tick,clock=lambda:NOW,monotonic=lambda:t[0],sleep=lambda n:t.__setitem__(0,t[0]+n))
            self.assertEqual(calls[0],2)
            self.assertEqual(result['status'],'NY_CLOSED')

    def test_once_mode_returns_failure_not_success_after_exception(self):
        with tempfile.TemporaryDirectory() as d:
            def fail():raise ValueError('private provider message')
            result=run_loop(d,once=True,tick=fail,clock=lambda:NOW)
            self.assertEqual(result['status'],'RUNTIME_ERROR')

    def test_workflow_preflight_missing_auth_fails_and_does_not_assert_feed_health(self):
        for present, expected in ((False,1),(True,0)):
            with patch('ibkr_feed_preflight.run',return_value={'runtime_auth_present':present}):
                self.assertEqual(preflight_main(['--require-auth']),expected)
        with patch('ibkr_feed_preflight.run',return_value={'runtime_auth_present':False}):
            self.assertEqual(preflight_main([]),0)
