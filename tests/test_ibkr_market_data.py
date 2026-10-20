import asyncio
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import pandas as pd

from ibkr_market_data import IBKRDataUnavailable, collect_history, normalize, resolve
from ibkr_feed_preflight import inspect

NOW=pd.Timestamp('2026-10-20T14:00:00Z')


def bars():
    times=pd.date_range('2026-10-20T13:20:00Z',periods=41,freq='min')
    return dict(time=[x.isoformat() for x in times],open=[100.]*41,high=[101.]*41,
                low=[99.]*41,close=[100.]*41,volume=[10.]*41,source='Last')


class Fake:
    def __init__(self,status='REALTIME',delay=None):
        self.calls=[];self.status=status;self.delay=delay
    async def __call__(self,name,args):
        self.calls.append((name,args))
        if name=='search_contracts':
            return {'results':[{'symbol':'ES','country_code':'US','exchange':'NYSE','underlying_contract_id':2,'sections':[{'security_type':'STK'}]},
                               {'symbol':'ES','country_code':'US','exchange':'CME','underlying_contract_id':1,'sections':[{'security_type':'FUT'}]}]}
        if name=='search_futures':
            return {'contracts':[{'contract_id':4,'exchange':'CME','contract_month':'202703','last_trading_date':'20270319'},
                                 {'contract_id':3,'exchange':'CME','contract_month':'202612','last_trading_date':'20261218'}]}
        if name=='get_price_snapshot':
            return {'top-status':{'status':self.status},'last':{'price':100.,'ts':int(NOW.timestamp())}}
        if name=='get_price_history':
            r=bars()
            if self.delay is not None:r['delayed']=self.delay
            return r
        raise AssertionError(name)


class IBKRDataTests(unittest.TestCase):
    def test_future_resolution_does_not_select_eversource_and_sorts_expiry(self):
        call=Fake()
        c=asyncio.run(resolve(call,'ES=F',NOW))
        self.assertEqual(c['contract_id'],3)
        self.assertEqual(c['exchange'],'CME')
        self.assertEqual(call.calls[0][1],{'query':'ES'})

    def test_complete_realtime_history_uses_native_exchange_and_exact_window(self):
        call=Fake()
        result=asyncio.run(collect_history(call,'ES',now=NOW,step_count=1000))
        self.assertEqual(len(result),40) # unfinished 14:00 bar removed
        self.assertTrue(result.attrs['live_feed_verified'])
        self.assertEqual(call.calls[-1][1]['exchange'],'CME')
        self.assertNotIn('period',call.calls[-1][1])
        self.assertEqual(result.attrs['latest_bar_age_seconds'],0)

    def test_frozen_or_delayed_feed_cannot_reach_detector(self):
        for status in ('FROZEN','DELAYED','UNAVAILABLE'):
            call=Fake(status)
            with self.assertRaises(IBKRDataUnavailable):
                asyncio.run(collect_history(call,'ES',now=NOW,step_count=1000))
            self.assertNotIn('get_price_history',[n for n,a in call.calls])
        with self.assertRaises(IBKRDataUnavailable):
            asyncio.run(collect_history(Fake(delay=15),'ES',now=NOW,step_count=1000))

    def test_stale_history_rejected_despite_realtime_snapshot(self):
        call=Fake()
        original=call.__call__
        async def wrapped(name,args):
            r=await original(name,args)
            if name=='get_price_history':
                r['time']=[(pd.Timestamp(t)-pd.Timedelta(hours=1)).isoformat() for t in r['time']]
            return r
        with self.assertRaises(IBKRDataUnavailable):
            asyncio.run(collect_history(wrapped,'ES',now=NOW,step_count=1000))

    def test_historical_request_does_not_certify_realtime_or_use_snapshot(self):
        call=Fake('FROZEN')
        result=asyncio.run(collect_history(call,'ES',now=NOW,period='5d',require_realtime=False))
        self.assertFalse(result.attrs['live_feed_verified'])
        self.assertEqual(call.calls[-1][1]['period'],'ONE_WEEK')
        self.assertNotIn('get_price_snapshot',[n for n,a in call.calls])

    def test_malformed_or_ambiguous_prices_rejected_without_repair(self):
        for change in ('nan','duplicate','naive','ohlc','length'):
            r=bars()
            if change=='nan':r['close'][0]=float('nan')
            if change=='duplicate':r['time'][1]=r['time'][0]
            if change=='naive':r['time'][0]='2026-10-20T13:20:00'
            if change=='ohlc':r['low'][0]=110
            if change=='length':r['close'].pop()
            with self.assertRaises((IBKRDataUnavailable, ValueError)):normalize(r)

    def test_missing_runtime_auth_is_explicit_and_makes_no_network_request(self):
        from ibkr_mcp_client import run_collection
        storage=type('Storage',(),{'get_tokens':AsyncMock(return_value=None),'get_client_info':AsyncMock(return_value=None)})()
        collector=AsyncMock()
        result=asyncio.run(run_collection(storage=storage,collector=collector))
        self.assertEqual(result['status'],'authorization_required')
        collector.assert_not_called()
        health=asyncio.run(inspect(storage))
        self.assertEqual(health['status'],'AUTHORIZATION_REQUIRED')
        self.assertFalse(health['feed_realtime_verified'])
        self.assertNotIn('tokens',health)

    def test_no_active_yahoo_imports_or_synthetic_coin_fallback(self):
        root=Path(__file__).resolve().parents[1]
        for path in root.glob('*.py'):
            text=path.read_text()
            self.assertNotIn('import yfinance',text,str(path))
            self.assertNotIn('api.coingecko.com',text,str(path))
        self.assertNotIn('yfinance',(root/'requirements.txt').read_text())
