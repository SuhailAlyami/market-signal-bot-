"""Strict ES recommendation gate. Experimental/incomplete events never publish."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import urllib.request
from zoneinfo import ZoneInfo


def recommendation(event, heartbeat, now):
    """Return a fully specified ES issue or a concrete blocking reason."""
    def age(value):
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None: raise ValueError('naive timestamp')
        return (now-parsed).total_seconds()
    try:
        if heartbeat.get('status') != 'ok': return None, 'unhealthy_feed'
        if event.get('signal_status') != 'COMPLETE' or event.get('notify_eligible') is not True:
            return None, 'conditions_not_complete'
        if event.get('state') != 'TRIGGER' or event.get('symbol') not in ('ES','ES=F','SPX'):
            return None, 'not_confirmed_es'
        symbol='SPX' if event['symbol']=='SPX' else 'ES'
        status = heartbeat['symbols'][event['symbol']]
        metadata = status['feed_metadata']
        if (status['status'] != 'ok' or metadata.get('source') != 'IBKR Gateway TWS API'
                or metadata.get('market_data_type') != 1 or not status.get('live_feed_verified')):
            return None, 'realtime_unverified'
        if not all(0 <= age(t) <= limit for t,limit in (
                (heartbeat['timestamp'],30),(metadata['last_trade_time'],10 if symbol=='SPX' else 60),
                (event['detected_at'],60),(event['bar_end'],90))):
            return None, 'stale_or_future_data'
        current = float(metadata['last_price'])
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
        if not math.isfinite(current) or not zone[0] <= current <= zone[1]:
            return None, 'price_outside_entry_zone'
        contract_text=''
        if symbol=='SPX':
            option=event['option_contract']
            bid,ask=float(option['bid']),float(option['ask'])
            if (option['symbol']!='SPX' or option['market_data_type']!=1 or not option['live_verified']
                or option['right']!=('C' if direction=='UP' else 'P') or int(option['contract_id'])<=0
                or option['expiry']!=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
                or not 0<=age(option['quote_time'])<=10 or not 0<bid<=ask
                or not all(math.isfinite(x) for x in (bid,ask,float(option['strike'])))
                or abs(float(option['strike'])/current-1)>.01 or (ask-bid)/((ask+bid)/2)>.15):
                return None,'spx_option_unverified_or_stale'
            contract_text=(f"العقد المرصود: SPX {option['expiry']} {option['right']} {option['strike']}\n"
                f"Bid: {bid} | Ask: {ask} | ConId: {option['contract_id']}\n"
                f"وقت استلام عرض العقد: {option['quote_time']} | المصدر: {option['source']}\n"
                'مستويات الدخول والوقف والأهداف أعلاه تخص مؤشر SPX؛ ليست أسعار خروج لعقد الخيار.\n')
        identity='|'.join((symbol,direction,event['bar_end'],event.get('rule_version','v1')))
        key = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return {'key':key,'title':f"[Suhail {symbol} {key}] {'UP' if direction=='UP' else 'DOWN'}",
            'body': ('رصد تجريبي بقواعد محددة؛ الأداء خارج العينة غير مثبت.\n' +
                ('الأصل: SPX | تأكيد مساعد من ES، دون تحويل أسعاره\n' if symbol=='SPX' else 'الأصل: ES (عقد مستقبلي؛ ليست توصية على خيارات SPX)\n') +
                f"الاتجاه: {direction}\nسبب الإشارة: {event['reason']}\n"
                f"منطقة الدخول: {zone}\nوقف الخسارة: {stop}\nالأهداف: {targets}\n"
                f"وقت الإشارة UTC: {event['detected_at']}\nالشمعة UTC: {event['bar_end']}\n"
                f"مصدر البيانات: {metadata['source']} — REALTIME\n" +
                contract_text+'تنبيه فقط؛ لا تنفيذ صفقات.\n'
                f"<!-- suhail-event:{key} -->")}, None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None, 'incomplete_conditions'


def deliver(events, heartbeat, directory, now=None):
    fixed_clock=now is not None
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
        try:
            gh = Path(os.environ['HUNTER_GH_EXECUTABLE']) if os.getenv('HUNTER_GH_EXECUTABLE') else Path.home()/'.local/share/suhail-hunter/gh/gh.exe'
        except RuntimeError:
            gh = Path('/nonexistent-gh')
        cli = False
        if not token and gh.is_file():
            try:
                cli = subprocess.run([str(gh),'auth','status','--hostname','github.com'],
                        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=5).returncode==0
            except (OSError,subprocess.TimeoutExpired):
                pass
        if not token and not cli:
            results.append({'status':'github_auth_unavailable','key':message['key']}); continue
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo):
            raise ValueError('Invalid repository')
        # Authentication can take time: recheck immediately before reserving/sending.
        if not fixed_clock:
            message,reason=recommendation(event,heartbeat,datetime.now(timezone.utc))
            if message is None:
                results.append({'status':'blocked','reason':reason});continue
        # Durable reservation before network: uncertain outcomes never auto-resend.
        with receipt.open('x',encoding='utf-8') as stream:
            json.dump({'status':'reserved','time':now.isoformat(),'key':message['key']},stream)
        try:
            if cli:
                body_path = directory/(message['key']+'.md')
                body_path.write_text(message['body'],encoding='utf-8')
                try:
                    result = subprocess.run([str(gh),'issue','create','--repo',repo,
                        '--title',message['title'],'--body-file',str(body_path)],
                        capture_output=True,text=True,timeout=20)
                    if result.returncode: raise RuntimeError('github_cli_delivery_failed')
                    url=result.stdout.strip()
                    if not re.fullmatch(r'https://github.com/'+re.escape(repo)+r'/issues/[0-9]+',url):
                        raise ValueError('github_receipt_unverified')
                    status={'status':'github_accepted','issue_number':int(url.rsplit('/',1)[-1]),'url':url}
                finally:
                    body_path.unlink(missing_ok=True)
                receipt.write_text(json.dumps(status),encoding='utf-8');results.append(status)
                continue
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
