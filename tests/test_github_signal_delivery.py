from datetime import datetime,timezone,timedelta
import tempfile
import unittest
from unittest.mock import patch
from github_signal_delivery import recommendation,deliver


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,22,4,tzinfo=timezone.utc)
        t=self.now.isoformat()
        self.event=dict(event_id='test',readiness='NOT_READY',signal_status='COMPLETE',notify_eligible=True,state='TRIGGER',
                        symbol='ES=F',detected_at=t,bar_end=t,entry_zone=[100,101],
                        stop_loss=99,targets=[102,103],direction='UP',reason='confirmed fixture')
        self.heartbeat=dict(status='ok',timestamp=t,symbols={'ES=F':dict(status='ok',live_feed_verified=True,
            feed_metadata=dict(source='IBKR Gateway TWS API',market_data_type=1,last_trade_time=t,last_price=100.5))})

    def test_complete_es_message(self):
        message,reason=recommendation(self.event,self.heartbeat,self.now)
        self.assertIsNone(reason); self.assertIn('ES',message['title'])
        for field in ('وقف الخسارة','الأهداف','منطقة الدخول','مصدر البيانات'): self.assertIn(field,message['body'])

    def test_incomplete_experimental_stale_future_and_wrong_levels_rejected(self):
        for change in [dict(signal_status='INCOMPLETE'),dict(targets=[]),dict(stop_loss=200),dict(symbol='SPX'),
                       dict(detected_at=(self.now-timedelta(seconds=61)).isoformat()),
                       dict(bar_end=(self.now+timedelta(seconds=1)).isoformat()),dict(entry_zone=[float('nan'),101])]:
            with self.subTest(change=change):
                message,reason=recommendation({**self.event,**change},self.heartbeat,self.now)
                self.assertIsNone(message); self.assertIsNotNone(reason)

    def test_price_must_still_be_in_entry_zone(self):
        self.heartbeat['symbols']['ES=F']['feed_metadata']['last_price']=105
        self.assertEqual(recommendation(self.event,self.heartbeat,self.now)[1],'price_outside_entry_zone')

    def test_uncertain_send_never_repeats(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{'GITHUB_TOKEN':'test'}):
            with patch('github_signal_delivery.urllib.request.urlopen',side_effect=TimeoutError) as send:
                first=deliver([self.event],self.heartbeat,directory,self.now)
                second=deliver([self.event],self.heartbeat,directory,self.now)
                self.assertEqual(first[0]['status'],'uncertain_no_automatic_resend')
                self.assertEqual(second[0]['status'],'deduplicated'); self.assertEqual(send.call_count,1)

    def test_missing_auth_does_not_attempt_network(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict('os.environ',{},clear=True):
            with patch('github_signal_delivery.urllib.request.urlopen') as send:
                result=deliver([self.event],self.heartbeat,directory,self.now)
                self.assertEqual(result[0]['status'],'github_auth_unavailable');send.assert_not_called()
