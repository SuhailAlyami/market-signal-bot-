"""Native SPX primary monitor; ES supplies explicitly lagged confirmation only."""
from datetime import datetime,timezone
import json
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

import pandas as pd
from ibapi.contract import Contract
from gateway_spx_probe import Probe
from hunter_runtime import HunterRuntime
from strategy_rules import candidate,features
from es_signal_plan import complete_plan
from spx_option_selector import OptionQuote,select_spx_0dte

UTC=timezone.utc


def supporting_frame(spx,es):
    """SPX OHLC untouched; derived Volume is labelled ES previous-minute evidence."""
    value=spx[['Open','High','Low','Close']].copy()
    # Explicit lag: the counterpart bar was already completed before SPX's bar.
    keys=spx.index-pd.Timedelta(minutes=1)
    volume=es.Volume.reindex(keys)
    present=volume.notna().to_numpy()
    value=value.iloc[present].copy();volume=volume.iloc[present]
    if len(value)<31:raise ValueError('missing_lagged_es_volume')
    value['Volume']=volume.to_numpy()
    value.attrs.update(spx.attrs,volume_source='ES previous completed minute; not SPX volume')
    return value


def index_frame(client,now=None):
    now=now or datetime.now(UTC)
    if client.lost or not client.isConnected():raise RuntimeError('spx_disconnected')
    if client.types.get(201)!=1:raise RuntimeError('spx_realtime_unverified')
    quotes=list(client.quotes.get(201,[]))
    times=[q for q in quotes if q.get('type')==45 and int(q.get('value','0'))>0]
    prices=[q for q in quotes if q.get('type')==4]
    if not times or not prices:raise RuntimeError('spx_live_timestamp_missing')
    trade=datetime.fromtimestamp(int(times[-1]['value']),UTC)
    if not 0<=(now-trade).total_seconds()<=10:raise RuntimeError('spx_index_stale')
    with client.lock:
        keys=sorted(client.rows)
        rows=[client.rows[k][:4] for k in keys]
    frame=pd.DataFrame(rows,index=pd.to_datetime(keys,unit='s',utc=True),columns=['Open','High','Low','Close'])
    frame.attrs.update(source='IBKR Gateway TWS API',symbol='SPX',security_type='IND',
        volume_semantics='index volume not published; no synthetic SPX volume',market_data_type=1,
        live_feed_verified=True,last_trade_time=trade.isoformat(),last_price=prices[-1]['price'],
        observed_at=now.isoformat(),bar_publication_latency_verified=False)
    completed=[k for k in keys if k+60<=now.timestamp()]
    if not completed or now.timestamp()-completed[-1]-60>90:raise RuntimeError('spx_bars_stale')
    return frame


def option_candidate(client,frame,direction,now=None):
    now=now or datetime.now(UTC);quotes=[];identities={}
    for req,contract in client.options.items():
        items=list(client.quotes.get(req,[]))
        bid=[q for q in items if q.get('type')==1];ask=[q for q in items if q.get('type')==2]
        # Require actual repeated book callbacks, not an initial frozen snapshot.
        if client.types.get(req)!=1 or len(bid)<2 or len(ask)<2:continue
        received=min(datetime.fromisoformat(bid[-1]['received_at']),datetime.fromisoformat(ask[-1]['received_at']))
        expiry=datetime.strptime(contract.lastTradeDateOrContractMonth[:8],'%Y%m%d').date().isoformat()
        q=OptionQuote('SPX',expiry,contract.right,contract.strike,bid[-1]['price'],ask[-1]['price'],
                      received,'IBKR Gateway TWS API; bid/ask local receipt',True)
        quotes.append(q);identities[(q.expiry,q.right,q.strike)]=contract.conId
    selected=select_spx_0dte(quotes,direction='CALL' if direction=='UP' else 'PUT',
        underlying=frame.attrs['last_price'],underlying_time=datetime.fromisoformat(frame.attrs['last_trade_time']),
        now=now,underlying_live_verified=True)
    if selected is None:return None
    return {'symbol':'SPX','contract_id':identities[(selected.expiry,selected.right,selected.strike)],
        'expiry':selected.expiry,'right':selected.right,'strike':selected.strike,'bid':selected.bid,'ask':selected.ask,
        'quote_time':selected.observed_at,'source':selected.source,'market_data_type':1,
        'live_verified':True,'quote_timestamp_kind':'local_receipt_not_exchange_timestamp'}


def connect_primary():
    client=Probe();client.options={}
    def run():
        try:client.connect('127.0.0.1',4001,clientId=20331024);client.run()
        except Exception:client.lost=True
    threading.Thread(target=run,daemon=True).start()
    try:
        if not client.ready.wait(12):raise RuntimeError('spx_handshake_timeout')
        contract=Contract();contract.symbol='SPX';contract.secType='IND';contract.exchange='CBOE';contract.currency='USD'
        contract=client.resolve(101,contract)
        if contract is None:raise RuntimeError('spx_contract_unresolved')
        client.reqMarketDataType(1);client.reqMktData(201,contract,'',False,False,[])
        client.reqHistoricalData(301,contract,'','7200 S','1 min','TRADES',0,2,True,[])
        client.reqSecDefOptParams(401,'SPX','','IND',contract.conId)
        client.chain_done.wait(15);client.history_ready.wait(15)
        # HMDS/secdef can finish before the first quote snapshot reaches us.
        deadline=time.monotonic()+10
        while time.monotonic()<deadline and not any(q.get('type') in (4,9) for q in client.quotes.get(201,[])):
            time.sleep(.25)
        # For permission sampling only, a historical last/close can locate strikes.
        # It never qualifies a recommendation; index_frame still requires a live timestamp.
        reference=[q['price'] for q in client.quotes.get(201,[]) if q.get('type')==4]
        if not reference:reference=[q['price'] for q in client.quotes.get(201,[]) if q.get('type')==9]
        today=datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%d')
        chains=[c for c in client.chains if c['trading_class']=='SPXW' and today in c['expirations']]
        if reference and chains:
            strikes=sorted(chains[0]['strikes'],key=lambda k:abs(k-reference[-1]))[:3]
            for n,(strike,right) in enumerate((s,r) for s in strikes for r in ('C','P')):
                option=Contract();option.symbol='SPX';option.secType='OPT';option.exchange='CBOE'
                option.currency='USD';option.tradingClass='SPXW';option.multiplier='100'
                option.lastTradeDateOrContractMonth=today;option.strike=strike;option.right=right
                resolved=client.resolve(110+n,option)
                if resolved:
                    req=210+n;client.options[req]=resolved;client.reqMktData(req,resolved,'',False,False,[])
        return client
    except Exception:
        client.disconnect();raise


def run(directory,es_fetch,stop):
    directory=Path(directory)/'spx';directory.mkdir(parents=True,exist_ok=True)
    def detect(bars,index):
        try:
            es=es_fetch();derived=supporting_frame(bars,es)
            # SPX direction is its own price direction; ES additionally confirms.
            if bars.index[index] not in derived.index:return None
            found=candidate(derived,derived.index.get_loc(bars.index[index]))
            if not found:return None
            key=bars.index[index]-pd.Timedelta(minutes=1)
            match=es.index.get_loc(key);support=features(es,match)
            if support is None or found['direction']*support['trend_5']<=0 or found['direction']*support['trend_15']<0:return None
            return found
        except (ValueError,KeyError,RuntimeError):return None
    runtime=HunterRuntime(directory/'state.json',directory/'shadow.jsonl',symbols=('SPX',),detector=detect)
    client=None;retry=0;failures=0;connected_at=0;last_status=None
    def journal(value):
        with (directory/'connection.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps({'time':datetime.now(UTC).isoformat(),**value})+'\n')
    while not stop.is_set():
        now=datetime.now(UTC);report={'time':now.isoformat(),'primary_symbol':'SPX','support_symbol':'ES',
            'orders_enabled':False,'options_scope':'three nearby strikes, both rights; not every chain contract'}
        try:
            if client is None:
                if time.monotonic()<retry:stop.wait(2);continue
                client=connect_primary();connected_at=time.monotonic()
            report.update(index_data_type=client.types.get(201),chain_classes=[c['trading_class'] for c in client.chains],
                          sampled_options=[{'contract_id':c.conId,'strike':c.strike,'right':c.right,
                             'expiry':c.lastTradeDateOrContractMonth,'market_data_type':client.types.get(req),
                             'callbacks':len(client.quotes.get(req,[]))} for req,c in client.options.items()],errors=client.errors)
            frame=None
            def fetch(symbol):
                nonlocal frame
                frame=index_frame(client);return frame
            result=runtime.poll(now,fetch,clock=lambda:datetime.now(UTC))
            report['heartbeat']=result['heartbeat'];report['status']=result['heartbeat']['status']
            if frame is None:
                try:index_frame(client)
                except RuntimeError as exc:report['blocker']=str(exc)
            else:
                from github_signal_delivery import deliver
                from telegram_signal_delivery import deliver as telegram_deliver
                for event in result['events']:
                    if event['state']!='TRIGGER':continue
                    es=es_fetch();derived=supporting_frame(frame,es)
                    last_key=pd.Timestamp(event['bar_end'])-pd.Timedelta(minutes=2)
                    support=features(es,es.index.get_loc(last_key)) if last_key in es.index else None
                    sign=1 if event['direction']=='UP' else -1
                    if support is None or sign*support['trend_5']<=0 or sign*support['trend_15']<0:
                        journal({'status':'signal_blocked','reason':'es_confirmation_lost'});continue
                    plan,reason=complete_plan(event,derived,tick_size=0.01)
                    option=option_candidate(client,frame,event['direction']) if plan else None
                    if not plan or option is None:
                        journal({'status':'signal_blocked','reason':reason or 'no_fresh_spx_option'});continue
                    plan['option_contract']=option;plan['support_symbol']='ES'
                    for channel,sender in [('github',deliver),('telegram',telegram_deliver)]:
                        try:
                            for receipt in sender([plan],result['heartbeat'],directory):journal({'channel':channel,**receipt})
                        except Exception as exc:journal({'channel':channel,'status':'unavailable','error_type':type(exc).__name__})
            if client.lost or time.monotonic()-connected_at>300 or report.get('blocker')=='spx_bars_stale':
                client.disconnect();client=None
            failures=0
        except Exception as exc:
            report.update(status='unavailable',blocker=type(exc).__name__)
            if client:client.disconnect();client=None
            failures+=1;retry=time.monotonic()+min(60,2**min(failures,6))
        if report.get('status')!=last_status:
            journal({'status':report.get('status'),'blocker':report.get('blocker')});last_status=report.get('status')
        temporary=directory/'status.tmp';temporary.write_text(json.dumps(report,indent=2),encoding='utf-8');temporary.replace(directory/'status.json')
        stop.wait(5)
    if client:client.disconnect()
