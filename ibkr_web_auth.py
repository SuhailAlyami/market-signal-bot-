"""Owner-gated hosted OAuth setup. No credentials or OAuth URLs in logs/health.

Tokens use the existing private storage OUTSIDE the checkout. On a free
ephemeral host, replacement loses the session; this does not promise uptime.
"""
import asyncio
import hmac
import os
import secrets
import threading
import time
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, make_response, redirect, request

TTL = 180
bp = Blueprint('ibkr_setup', __name__)
_lock = threading.Lock()
_active = None


class WebAuthorization:
    def __init__(self, origin):
        self.callback_url = origin + '/ibkr/callback'
        self.session = secrets.token_urlsafe(32)
        self.created = time.monotonic()
        self.url = None
        self.state = None
        self.result = None
        self.status = 'starting'
        self.event = threading.Event()

    def alive(self):
        return time.monotonic() - self.created < TTL

    def set_redirect(self, url):
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if (parsed.scheme != 'https' or parsed.netloc != 'api.ibkr.com'
                or parsed.path != '/oauth2/authorize'
                or query.get('scope') != ['mcp.read']
                or query.get('redirect_uri') != [self.callback_url]
                or len(query.get('state', [])) != 1
                or not query['state'][0]
                or query.get('code_challenge_method') != ['S256']
                or not query.get('code_challenge')):
            raise ValueError('unexpected_authorization_request')
        self.state = query['state'][0]
        self.url = url
        self.status = 'login_required'

    async def wait(self):
        remaining = max(0, TTL - (time.monotonic() - self.created))
        if not await asyncio.to_thread(self.event.wait, remaining):
            raise TimeoutError('authorization_expired')
        return self.result

    def accept(self, code, state):
        with _lock:
            if (not self.alive() or self.status != 'login_required' or not code
                    or not self.state or not hmac.compare_digest(state, self.state)):
                return False
            self.result = (code, state)
            self.status = 'verifying'
            self.event.set()
            return True


def _origin():
    value = os.getenv('IBKR_WEB_ORIGIN', '').rstrip('/')
    parsed = urlparse(value)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.path or parsed.query or parsed.fragment):
        return None
    return value


def _owner_session():
    with _lock:
        current = _active
    cookie = request.cookies.get('__Host-hunter-setup', '')
    return current if (current and current.alive() and cookie
                       and hmac.compare_digest(cookie, current.session)) else None


def _run(current):
    try:
        from ibkr_mcp_client import run_collection
        # Establish the authorized READ-ONLY transport; do not fetch prices or
        # account data as a side effect of signing in.
        async def authorized(tools):
            return {'status': 'authorized'}
        result = asyncio.run(run_collection(authorize=True, collector=authorized,
                                             web_authorization=current))
        current.status = 'authorized' if result.get('status') == 'authorized' else 'failed'
    except Exception:
        current.status = 'failed'
    finally:
        current.url = None
        current.state = None
        current.result = None


@bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    return response


@bp.route('/ibkr/setup', methods=['GET', 'POST'])
def setup():
    global _active
    origin = _origin()
    key = os.getenv('IBKR_WEB_SETUP_KEY', '')
    if not origin or len(key) < 32:
        return 'Hosted setup is not configured.', 503
    if request.method == 'GET':
        return '<meta charset="utf-8"><h1>ربط سهيل هنتر بـ IBKR للقراءة فقط</h1><p>أدخل مفتاح إعداد الخدمة من لوحة Render. لا تدخل كلمة مرور IBKR هنا.</p><form method="post"><input type="password" name="key" required autocomplete="off"><button>بدء الربط</button></form><p>خطة Render المجانية قد تنام وتفقد جلسة الربط عند استبدال الخادم.</p>'
    if request.headers.get('Origin') != origin:
        return 'Forbidden', 403
    candidate = request.form.get('key', '')
    if len(candidate) > 512 or not hmac.compare_digest(candidate, key):
        return 'Forbidden', 403
    with _lock:
        if _active and _active.alive():
            return 'A setup session is already active. Wait three minutes.', 409
        _active = WebAuthorization(origin)
        current = _active
    threading.Thread(target=_run, args=(current,), daemon=True, name='ibkr-web-setup').start()
    response = make_response(redirect('/ibkr/setup/status', code=303))
    response.set_cookie('__Host-hunter-setup', current.session, secure=True,
                        httponly=True, samesite='Lax', path='/', max_age=TTL)
    return response


@bp.get('/ibkr/setup/status')
def status():
    current = _owner_session()
    if not current:
        return 'Setup session expired.', 403
    if current.status == 'login_required':
        return '<meta charset="utf-8"><p>تسجيل الدخول يتم في موقع IBKR فقط.</p><a href="/ibkr/setup/login">فتح IBKR للموافقة على قراءة السوق</a>'
    if current.status == 'authorized':
        return '<meta charset="utf-8"><p>تم ربط القارئ. هذا ليس إثبات وصول بيانات السوق أو نجاح التنبيهات. تحقق من حالة الخدمة وسجلاتها.</p>'
    if current.status == 'failed':
        return 'Authorization failed. No trading permissions were requested.', 502
    response = make_response('Preparing or verifying read-only connection. This page refreshes automatically.')
    response.headers['Refresh'] = '2'
    return response


@bp.get('/ibkr/setup/login')
def login():
    current = _owner_session()
    if not current or current.status != 'login_required' or not current.url:
        return 'Setup session unavailable.', 403
    return redirect(current.url, code=303)


@bp.get('/ibkr/callback')
def callback():
    current = _owner_session()
    codes, states = request.args.getlist('code'), request.args.getlist('state')
    if (not current or len(codes) != 1 or len(states) != 1
            or len(codes[0]) > 4096 or len(states[0]) > 512
            or not current.accept(codes[0], states[0])):
        return 'Authorization rejected or expired.', 400
    return redirect('/ibkr/setup/status', code=303)
