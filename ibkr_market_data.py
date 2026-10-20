"""Project-wide IBKR market data. No secondary provider or implicit login.

Historical bars retain their provider semantics. Realtime callers additionally
require REALTIME snapshot entitlement, recent last trade and fresh complete bars.
OAuth belongs to the running host, outside the repo and all cached artifacts.
"""
import asyncio
from datetime import datetime, timezone
from functools import partial

import numpy as np
import pandas as pd

from ibkr_mcp import unwrap, inspect_snapshot

SOURCE = 'IBKR MCP'
STEPS = {'1m':('ONE_MIN',60), '2m':('TWO_MINS',120), '5m':('FIVE_MINS',300),
         '15m':('FIFTEEN_MINS',900), '30m':('THIRTY_MINS',1800), '1h':('ONE_HOUR',3600),
         '60m':('ONE_HOUR',3600), '1d':('ONE_DAY',86400)}
PERIODS = {'1d':'ONE_DAY','2d':'TWO_DAYS','3d':'THREE_DAYS','5d':'ONE_WEEK','7d':'ONE_WEEK',
           '1mo':'ONE_MONTH','3mo':'THREE_MONTHS','6mo':'SIX_MONTHS','1y':'ONE_YEAR'}


class IBKRDataUnavailable(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def normalize(raw):
    raw = unwrap(raw)
    if raw.get('error'):
        raise IBKRDataUnavailable('history_provider_error')
    arrays = [raw.get(k) for k in ('time','open','high','low','close','volume')]
    if any(not isinstance(a,list) for a in arrays) or len({len(a) for a in arrays}) != 1 or not len(arrays[0]):
        raise IBKRDataUnavailable('invalid_history_arrays')
    index = pd.to_datetime(arrays[0], utc=True, errors='raise')
    # Require explicit offsets, never interpret an ambiguous local timestamp.
    if any(pd.Timestamp(t).tz is None for t in arrays[0]):
        raise IBKRDataUnavailable('naive_history_timestamp')
    data = pd.DataFrame(dict(zip(('Open','High','Low','Close','Volume'), arrays[1:])), index=index).astype(float)
    if not index.is_unique or not index.is_monotonic_increasing or not np.isfinite(data).all().all():
        raise IBKRDataUnavailable('invalid_history_values')
    if ((data.Low<=0)|(data.Volume<0)|(data.High<data[['Open','Close','Low']].max(axis=1))|
        (data.Low>data[['Open','Close']].min(axis=1))).any():
        raise IBKRDataUnavailable('invalid_history_ohlcv')
    data.attrs.update(source=SOURCE, history_source=raw.get('source'), delayed=raw.get('delayed'))
    return data


async def resolve(call, symbol, now):
    # Legacy =F identifiers are input aliases only, never sent to IBKR.
    root = {'^GSPC':'SPX','^NDX':'NDX','^VIX':'VIX'}.get(symbol, symbol.removesuffix('=F').removeprefix('^'))
    future = symbol.endswith('=F') or root in ('ES','NQ')
    security = 'FUT' if future else 'IND' if symbol.startswith('^') or root=='SPX' else 'STK'
    found = unwrap(await call('search_contracts', {'query':root}))
    matches = [r for r in found.get('results',[]) if r.get('symbol')==root and
               any(s.get('security_type')==security for s in r.get('sections',[])) and r.get('country_code')=='US']
    if len(matches)!=1:
        raise IBKRDataUnavailable('ambiguous_or_missing_contract')
    row = matches[0]
    if future:
        ladder = unwrap(await call('search_futures', {'underlying_contract_id':row['underlying_contract_id']}))
        valid = sorted((c for c in ladder.get('contracts',[]) if c.get('exchange')==row['exchange'] and
                        c.get('last_trading_date','')>now.strftime('%Y%m%d')),
                       key=lambda c:c['contract_month'])
        if not valid:
            raise IBKRDataUnavailable('no_active_future')
        contract = valid[0]
        # Deterministic front expiry; do not claim a liquidity-based roll choice.
        return {'contract_id':contract['contract_id'],'exchange':contract['exchange'],
                'security_type':'FUT','contract_month':contract['contract_month'],
                'last_trading_date':contract['last_trading_date']}
    return {'contract_id':row['underlying_contract_id'], 'exchange':row['exchange'], 'security_type':security}


async def collect_history(call, symbol, *, interval='1m', period=None, step_count=None,
                          require_realtime=True, now=None):
    fixed = now is not None
    now = pd.Timestamp(now if fixed else datetime.now(timezone.utc))
    if now.tz is None:
        raise ValueError('aware_clock_required')
    if interval not in STEPS or (period is None)==(step_count is None):
        raise ValueError('supported_interval_and_exactly_one_history_window_required')
    contract = await resolve(call,symbol,now)
    snapshot = None
    if require_realtime:
        snapshot = inspect_snapshot(await call('get_price_snapshot', {
            'contract_id':contract['contract_id'],'exchange':contract['exchange'],
            'market_data_names':['last','top_status']}),now.to_pydatetime() if fixed else datetime.now(timezone.utc),max_age_seconds=60)
        if not snapshot['last_live_verified']:
            raise IBKRDataUnavailable('snapshot_not_realtime_or_not_fresh')
    args = {k:contract[k] for k in ('contract_id','exchange','security_type')}
    args.update(outside_rth=True, step=STEPS[interval][0])
    if period is not None:
        if period not in PERIODS:
            raise IBKRDataUnavailable('unsupported_history_period')
        args['period'] = PERIODS[period]
    else:
        if not isinstance(step_count,int) or not 1<=step_count<=1000:
            raise ValueError('bounded_history_count_required')
        args['step_count'] = step_count
    raw = unwrap(await call('get_price_history',args))
    data = normalize(raw)
    # Receipt time is measured after history returns, not before network latency.
    receipt = now if fixed else pd.Timestamp(datetime.now(timezone.utc))
    seconds = STEPS[interval][1]
    data = data.loc[data.index+pd.Timedelta(seconds=seconds)<=receipt]
    if data.empty:
        raise IBKRDataUnavailable('no_complete_bars')
    age = (receipt-data.index[-1]-pd.Timedelta(seconds=seconds)).total_seconds()
    # delayed=0 is explicitly undelayed; absence does not by itself prove live.
    delayed = raw.get('delayed')
    if require_realtime and (delayed not in (None,0,False) or not 0<=age<=max(120, seconds+60) or
                             not 0<=(receipt-pd.Timestamp(snapshot['last_trade_at'])).total_seconds()<=60):
        raise IBKRDataUnavailable('delayed_or_stale_history')
    data.attrs.update(source=SOURCE, contract=contract, observed_at=receipt.isoformat(),
                      feed_status=snapshot['feed_status'] if snapshot else 'HISTORICAL_UNVERIFIED',
                      live_feed_verified=bool(snapshot and snapshot['last_live_verified']),
                      snapshot_live_verified=bool(snapshot and snapshot['last_live_verified']),
                      bar_publication_latency_verified=False,
                      latest_bar_age_seconds=age, history_request=args, raw_adjusted=False)
    return data


async def request_async(symbol, **kwargs):
    from ibkr_mcp_client import run_collection
    result = await run_collection(collector=partial(collect_history, symbol=symbol, **kwargs))
    if not isinstance(result,pd.DataFrame):
        raise IBKRDataUnavailable(result.get('reason') or result.get('status','ibkr_unavailable'))
    return result


def fetch_bars(symbol, *, interval='1m', period=None, step_count=None, require_realtime=True):
    if period is None and step_count is None:
        step_count=1000
    return asyncio.run(request_async(symbol, interval=interval, period=period, step_count=step_count,
                                     require_realtime=require_realtime))


class Ticker:
    """Small migration facade for older history-only scanners; IBKR exclusively."""
    def __init__(self,symbol):
        self.symbol=symbol

    def history(self,period='5d',interval='5m',auto_adjust=False,raise_errors=True,require_realtime=True,**kwargs):
        if kwargs:
            raise IBKRDataUnavailable('unsupported_history_arguments')
        # auto_adjust retained as a call compatibility argument; native broker
        # OHLCV are NOT adjusted or synthesized. Metadata explicitly says so.
        return fetch_bars(self.symbol,period=period,interval=interval,require_realtime=require_realtime)
