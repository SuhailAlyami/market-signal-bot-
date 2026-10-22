"""Authenticated data-only HTTPS ingress. Never exposes an IB trading socket."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.request

from flask import Blueprint, jsonify, request
import pandas as pd

from hunter_runtime import HunterRuntime
from es_signal_plan import complete_plan

bp = Blueprint('gateway_relay', __name__)
_lock = threading.Lock()
_runtime = None
_seen = {}
_health = {'status':'awaiting_gateway','source':'IBKR Gateway HTTPS relay','symbols':{}}


def enabled():
    return os.getenv('GATEWAY_RELAY_ENABLED','false').lower()=='true'


def health():
    result=json.loads(json.dumps(_health))
    if result.get('timestamp'):
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(result['timestamp'])).total_seconds()
        result['heartbeat_age_seconds']=age
        if age>30: result['status']='gateway_relay_stale'
    return result


def signature(secret, timestamp, nonce, raw):
    return hmac.new(secret.encode(),timestamp.encode()+b'\n'+nonce.encode()+b'\n'+raw,hashlib.sha256).hexdigest()


def decode_frame(payload, now):
    if payload['symbol']!='ES' or payload['contract']['security_type']!='FUT' or payload['contract']['exchange']!='CME':
        raise ValueError('not_native_es_future')
    if payload['contract']['expiry'] <= now.strftime('%Y%m%d'):
        raise ValueError('expired_contract')
    attrs=payload['metadata']
    if attrs.get('source')!='IBKR Gateway TWS API' or attrs.get('market_data_type')!=1:
        raise ValueError('realtime_unverified')
    for name,limit in [('observed_at',30),('last_trade_time',60)]:
        value=datetime.fromisoformat(attrs[name])
        if value.tzinfo is None or not 0<=(now-value).total_seconds()<=limit:
            raise ValueError('stale_or_future_quote')
    if not attrs.get('live_feed_verified') or not isinstance(payload['bars'],list) or not 31<=len(payload['bars'])<=180:
        raise ValueError('incomplete_feed')
    rows=payload['bars']
    frame=pd.DataFrame([r[1:] for r in rows],index=pd.to_datetime([r[0] for r in rows],unit='s',utc=True),
                       columns=['Open','High','Low','Close','Volume'])
    frame.attrs.update(attrs)
    return frame


@bp.route('/gateway/ingest',methods=['POST'])
def ingest():
    global _runtime,_health
    secret=os.getenv('GATEWAY_RELAY_SECRET','')
    if not enabled() or len(secret)<32: return jsonify(status='disabled'),503
    if request.content_length is None or request.content_length>98304:
        return jsonify(status='invalid_size'),413
    raw=request.get_data(cache=False)
    timestamp=request.headers.get('X-Gateway-Time','');nonce=request.headers.get('X-Gateway-Nonce','')
    try:
        age=time.time()-float(timestamp)
        if not 0<=age<=30 or not 16<=len(nonce)<=100: raise ValueError()
    except ValueError:
        return jsonify(status='invalid_auth_time'),401
    if not hmac.compare_digest(signature(secret,timestamp,nonce,raw),request.headers.get('X-Gateway-Signature','')):
        return jsonify(status='unauthorized'),401
    with _lock:
        now=datetime.now(timezone.utc)
        for key in list(_seen):
            if time.time()-_seen[key]>60: del _seen[key]
        if nonce in _seen: return jsonify(status='replayed_request'),409
        if len(_seen)>=512: return jsonify(status='too_many_requests'),429
        _seen[nonce]=time.time()
        try:
            payload=json.loads(raw)
            frame=decode_frame(payload,now)
        except (KeyError,ValueError,TypeError,OverflowError):
            return jsonify(status='invalid_or_stale_feed'),422
        if _runtime is None:
            directory=Path(os.getenv('HUNTER_STATE_DIR','.hunter-state'))/'relay'
            _runtime=HunterRuntime(directory/'state.json',directory/'shadow.jsonl',symbols=('ES=F',))
        result=_runtime.poll(now,lambda symbol:frame,clock=lambda:datetime.now(timezone.utc))
        _health=result['heartbeat'];_health['transport']='authenticated_gateway_https'
        primary=payload.get('primary_status')
        if isinstance(primary,dict):
            # Only operational metadata is public; no option quotes or credentials.
            allowed=('primary_symbol','support_symbol','status','blocker','time','index_data_type','sampled_option_count')
            _health['primary']={k:primary[k] for k in allowed if k in primary}
            try:
                age=(now-datetime.fromisoformat(primary['time'])).total_seconds()
                if not 0<=age<=30:_health['primary']['status']='stale_primary_monitor'
            except (KeyError,ValueError,TypeError):
                _health['primary']['status']='unverified_primary_monitor'
        plans=[];blocked=[]
        for event in result['events']:
            plan,reason=complete_plan(event,frame)
            if plan: plans.append(plan)
            elif event.get('state')=='TRIGGER': blocked.append(reason)
        return jsonify(heartbeat=_health,events=plans,blocked=blocked,orders_enabled=False)


def push_frame(frame,contract,url,secret,primary_status=None):
    # No redirects: never forward authentication signatures to another host.
    if url!='https://market-signal-bot-sw7t.onrender.com/gateway/ingest':
        raise ValueError('unexpected_relay_destination')
    payload={'symbol':'ES','contract':{'security_type':'FUT','exchange':'CME',
             'contract_id':contract.conId,'expiry':contract.lastTradeDateOrContractMonth},
             'metadata':dict(frame.attrs),'bars':[[int(index.timestamp()),*[float(v) for v in row]]
              for index,row in frame.tail(180).iterrows()]}
    if primary_status is not None:payload['primary_status']=primary_status
    raw=json.dumps(payload,allow_nan=False,separators=(',',':')).encode()
    timestamp=str(time.time());nonce=secrets.token_hex(16)
    headers={'Content-Type':'application/json','X-Gateway-Time':timestamp,'X-Gateway-Nonce':nonce,
             'X-Gateway-Signature':signature(secret,timestamp,nonce,raw)}
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs): return None
    with urllib.request.build_opener(NoRedirect).open(urllib.request.Request(url,data=raw,headers=headers),timeout=15) as response:
        result=json.load(response)
    if not isinstance(result.get('events'),list) or not isinstance(result.get('heartbeat'),dict):
        raise ValueError('invalid_relay_response')
    return result
