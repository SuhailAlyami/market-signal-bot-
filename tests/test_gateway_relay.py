from datetime import datetime,timezone
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch,Mock

from flask import Flask
import pandas as pd
import gateway_relay as relay
from es_signal_plan import complete_plan


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.frame=pd.DataFrame(index=pd.date_range('2026-10-22T03:00Z',periods=32,freq='min'))
        self.event=dict(symbol='ES=F',state='TRIGGER',direction='UP',bar_end='2026-10-22T03:32:00+00:00',
                        invalidation=99,event_id='test')
        self.features=dict(atr=2.,close=100.,rvol=1.5,trend_5=1.,trend_15=.5,move=.5)

    def test_complete_tick_aligned_plan_without_performance_claim(self):
        with patch('es_signal_plan.causal_features',return_value=self.features):
            plan,reason=complete_plan(self.event,self.frame)
        self.assertIsNone(reason)
        self.assertEqual(plan['entry_zone'],[99.75,100.25])
        self.assertEqual(plan['targets'],[101.5,102.75])
        self.assertEqual(plan['research_readiness'],'NOT_READY')

    def test_rechecks_volume_trend_and_risk(self):
        for change in [dict(rvol=.5),dict(trend_5=-1),dict(trend_15=-1),dict(move=-1),dict(atr=.1)]:
            with self.subTest(change=change),patch('es_signal_plan.causal_features',return_value={**self.features,**change}):
                self.assertIsNone(complete_plan(self.event,self.frame)[0])

    def test_does_not_plan_setup_or_missing_history(self):
        self.assertIsNone(complete_plan({**self.event,'state':'SETUP'},self.frame)[0])
        self.assertIsNone(complete_plan({**self.event,'bar_end':'2026-10-22T04:00:00+00:00'},self.frame)[0])


class RelayTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__);self.app.register_blueprint(relay.bp)
        self.client=self.app.test_client();self.secret='x'*40
        relay._seen.clear()
        self.env=patch.dict(os.environ,{'GATEWAY_RELAY_ENABLED':'true','GATEWAY_RELAY_SECRET':self.secret})
        self.env.start();self.addCleanup(self.env.stop)
        now=datetime.now(timezone.utc)
        self.payload={'symbol':'ES','contract':{'security_type':'FUT','exchange':'CME','expiry':'20991231'},
            'metadata':{'source':'IBKR Gateway TWS API','market_data_type':1,'live_feed_verified':True,
                        'last_trade_time':now.isoformat(),'observed_at':now.isoformat(),'last_price':100},
            'bars':[[int(now.timestamp())-60*i,100,101,99,100,30] for i in reversed(range(32))]}

    def post(self,payload=None,nonce='a'*32,signature=True,timestamp=None):
        raw=json.dumps(payload or self.payload).encode();timestamp=timestamp or str(time.time())
        headers={'X-Gateway-Time':timestamp,'X-Gateway-Nonce':nonce,
                 'X-Gateway-Signature':relay.signature(self.secret,timestamp,nonce,raw) if signature else 'bad'}
        return self.client.post('/gateway/ingest',data=raw,headers=headers,content_type='application/json')

    def test_auth_stale_time_and_replay(self):
        self.assertEqual(self.post(signature=False).status_code,401)
        self.assertEqual(self.post(timestamp=str(time.time()-40)).status_code,401)
        runtime=Mock();runtime.poll.return_value={'heartbeat':{'status':'ok','timestamp':datetime.now(timezone.utc).isoformat()},'events':[]}
        with patch.object(relay,'_runtime',runtime):
            self.assertEqual(self.post().status_code,200)
            self.assertEqual(self.post().status_code,409)
            self.assertEqual(runtime.poll.call_count,1)

    def test_reject_stale_feed_wrong_symbol_and_delayed(self):
        self.payload['metadata']['last_trade_time']='2020-01-01T00:00:00+00:00'
        self.assertEqual(self.post().status_code,422)
        self.payload['metadata']['last_trade_time']=datetime.now(timezone.utc).isoformat()
        self.payload['metadata']['market_data_type']=3
        self.assertEqual(self.post(nonce='b'*32).status_code,422)
        self.payload['metadata']['market_data_type']=1;self.payload['symbol']='SPX'
        self.assertEqual(self.post(nonce='c'*32).status_code,422)

    def test_disabled_without_secret_and_stale_health(self):
        with patch.dict(os.environ,{'GATEWAY_RELAY_SECRET':''}):
            self.assertEqual(self.post().status_code,503)
        with patch.object(relay,'_health',{'status':'ok','timestamp':'2020-01-01T00:00:00+00:00'}):
            self.assertEqual(relay.health()['status'],'gateway_relay_stale')

    def test_primary_health_exposes_status_without_book_or_secrets(self):
        self.payload['primary_status']={'primary_symbol':'SPX','support_symbol':'ES','status':'degraded',
            'time':datetime.now(timezone.utc).isoformat(),'blocker':'spx_index_stale',
            'option_quotes':[{'bid':1,'ask':2}],'secret':'fixture-not-a-secret'}
        runtime=Mock();runtime.poll.return_value={'heartbeat':{'status':'ok','timestamp':datetime.now(timezone.utc).isoformat()},'events':[]}
        with patch.object(relay,'_runtime',runtime):
            response=self.post()
        primary=response.json['heartbeat']['primary']
        self.assertEqual(primary['primary_symbol'],'SPX')
        self.assertNotIn('option_quotes',primary);self.assertNotIn('secret',primary)
