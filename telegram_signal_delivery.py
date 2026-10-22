"""Independent Telegram delivery, current-user encrypted credentials, one TEST."""
from datetime import datetime,timezone
import json
from pathlib import Path
import urllib.request
import urllib.parse

from github_signal_delivery import recommendation


def default_config():
    return Path.home()/'.local/share/suhail-hunter/telegram/credentials.dpapi'


def load_credentials(path=None):
    import win32crypt
    from ibkr_mcp_client import _oauth_path_is_private
    path=Path(path or default_config())
    if not path.exists():return None
    if not _oauth_path_is_private(path):raise PermissionError('Private credential ACL required')
    raw=win32crypt.CryptUnprotectData(path.read_bytes(),None,None,None,0)[1]
    return json.loads(raw.decode('utf-8'))


def save_credentials(token,chat_id,path=None):
    import re
    import win32crypt
    from ibkr_mcp_client import _protect_oauth_path
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]{20,}',token.strip()):raise ValueError('Invalid bot token format')
    if not re.fullmatch(r'-?[0-9]+|@[A-Za-z0-9_]{5,}',chat_id.strip()):raise ValueError('Invalid chat identifier')
    path=Path(path or default_config());path.parent.mkdir(parents=True,exist_ok=True)
    _protect_oauth_path(path.parent,directory=True)
    raw=json.dumps({'token':token.strip(),'chat_id':chat_id.strip()}).encode()
    sealed=win32crypt.CryptProtectData(raw,'Suhail Hunter Telegram',None,None,None,0)
    temporary=path.with_suffix('.tmp');temporary.touch();_protect_oauth_path(temporary)
    temporary.write_bytes(sealed);temporary.replace(path)


def send_once(credentials,text,receipt):
    receipt=Path(receipt)
    if receipt.exists():return {'status':'deduplicated'}
    receipt.parent.mkdir(parents=True,exist_ok=True)
    with receipt.open('x',encoding='utf-8') as stream:
        json.dump({'status':'reserved','time':datetime.now(timezone.utc).isoformat()},stream)
    try:
        data=urllib.parse.urlencode({'chat_id':credentials['chat_id'],'text':text}).encode()
        req=urllib.request.Request('https://api.telegram.org/bot'+credentials['token']+'/sendMessage',data=data)
        with urllib.request.urlopen(req,timeout=10) as response:result=json.load(response)
        if not result.get('ok'):raise ValueError('Telegram did not accept message')
        status={'status':'telegram_accepted','message_id':result['result']['message_id'],
                'time':datetime.now(timezone.utc).isoformat(),'human_read_verified':False}
    except Exception as exc:
        status={'status':'uncertain_no_automatic_resend','error_type':type(exc).__name__,
                'http_status':getattr(exc,'code',None)}
    receipt.write_text(json.dumps(status),encoding='utf-8');return status


def verify_once(directory,heartbeat):
    if heartbeat.get('status')!='ok':return None
    credentials=load_credentials()
    if not credentials:return {'status':'telegram_credentials_unavailable'}
    receipt=Path(directory)/'telegram-delivery'/'verification.json'
    if receipt.exists():return None
    return send_once(credentials,'🧪 تحقق واحد فقط — سهيل هنتر\n'
                     'هذه رسالة اختبار اتصال وليست توصية تداول.\n'
                     'رصد ES اللحظي مفعّل؛ لا صفقات. UTC: '+datetime.now(timezone.utc).isoformat(),receipt)


def deliver(events,heartbeat,directory):
    credentials=load_credentials()
    if not credentials:return []
    results=[]
    for event in events:
        message,reason=recommendation(event,heartbeat,datetime.now(timezone.utc))
        if not message:
            results.append({'status':'blocked','reason':reason});continue
        body=message['body'].split('<!--',1)[0]
        results.append(send_once(credentials,body,Path(directory)/'telegram-delivery'/(message['key']+'.json')))
    return results
