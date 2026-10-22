"""Strict ES recommendation gate. Experimental/incomplete events never publish."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import urllib.request


def recommendation(event, heartbeat, now):
    """Return a fully specified ES issue or a concrete blocking reason."""
    def age(value):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None: raise ValueError('naive timestamp')
        return (now-parsed).total_seconds()
    try:
        if heartbeat.get('status') != 'ok': return None, 'unhealthy_feed'
        if event.get('readiness') != 'READY' or event.get('notify_eligible') is not True:
            return None, 'detector_not_ready'
        if event.get('state') != 'TRIGGER' or event.get('symbol') not in ('ES','ES=F'):
            return None, 'not_confirmed_es'
        status = heartbeat['symbols'][event['symbol']]
        metadata = status['feed_metadata']
        if (status['status'] != 'ok' or metadata.get('source') != 'IBKR Gateway TWS API'
                or metadata.get('market_data_type') != 1 or not status.get('live_feed_verified')):
            return None, 'realtime_unverified'
        if not all(0 <= age(t) <= limit for t,limit in (
                (heartbeat['timestamp'],30),(metadata['last_trade_time'],60),
                (event['detected_at'],60),(event['bar_end'],90))):
            return None, 'stale_or_future_data'
        zone = [float(x) for x in event['entry_zone']]
        targets = [float(x) for x in event['targets']]
        stop = float(event['stop_loss'])
        if len(zone)!=2 or len(targets)<2 or not all(math.isfinite(x) and x>0 for x in zone+targets+[stop]):
            return None, 'invalid_levels'
        direction = event['direction']
        valid = (stop < zone[0] <= zone[1] < targets[0] < targets[1] if direction=='UP' else
                 targets[1] < targets[0] < zone[0] <= zone[1] < stop if direction=='DOWN' else False)
        if not valid or not str(event['reason']).strip() or not str(event['event_id']).strip():
            return None, 'inconsistent_or_missing_conditions'
        key = hashlib.sha256(str(event['event_id']).encode()).hexdigest()[:24]
        return {'key':key,'title':f"[Suhail ES {key}] {'UP' if direction=='UP' else 'DOWN'}",
            'body': ('الأصل: ES (عقد مستقبلي؛ ليست توصية على خيارات SPX)\n'
                f"الاتجاه: {direction}\nسبب الإشارة: {event['reason']}\n"
                f"منطقة الدخول: {zone}\nوقف الخسارة: {stop}\nالأهداف: {targets}\n"
                f"وقت الإشارة UTC: {event['detected_at']}\nالشمعة UTC: {event['bar_end']}\n"
                f"مصدر البيانات: {metadata['source']} — REALTIME\n"
                'تنبيه فقط؛ لا تنفيذ صفقات.\n'
                f"<!-- suhail-es-event:{key} -->")}, None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'incomplete_conditions'


def deliver(events, heartbeat, directory, now=None):
    now = now or datetime.now(timezone.utc)
    directory = Path(directory)/'github-delivery'; directory.mkdir(parents=True,exist_ok=True)
    results = []
    for event in events:
        message, reason = recommendation(event, heartbeat, now)
        if not message:
            results.append({'event_id':event.get('event_id'),'status':'blocked','reason':reason})
            continue
        receipt = directory/(message['key']+'.json')
        if receipt.exists():
            results.append({'status':'deduplicated','key':message['key']}); continue
        token = os.getenv('GITHUB_TOKEN','')
        repo = os.getenv('HUNTER_GITHUB_REPOSITORY','SuhailAlyami/market-signal-bot-')
        if not token:
            results.append({'status':'github_auth_unavailable','key':message['key']}); continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
            raise ValueError('Invalid repository')
        # Durable reservation before network: uncertain outcomes never auto-resend.
        with receipt.open('x',encoding='utf-8') as stream:
            json.dump({'status':'reserved','time':now.isoformat(),'key':message['key']},stream)
        try:
            request = urllib.request.Request(f'https://api.github.com/repos/{repo}/issues',
                data=json.dumps({k:message[k] for k in ('title','body')}).encode(),
                headers={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json',
                         'Content-Type':'application/json','User-Agent':'Suhail-Hunter-readonly'})
            with urllib.request.urlopen(request,timeout=10) as response:
                result=json.load(response)
            status={'status':'github_accepted','issue_number':result['number'],'url':result['html_url']}
        except Exception as exc:
            status={'status':'uncertain_no_automatic_resend','error_type':type(exc).__name__}
        receipt.write_text(json.dumps(status),encoding='utf-8'); results.append(status)
    return results
