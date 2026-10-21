import asyncio
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode
from flask import Flask
import ibkr_web_auth as web

ORIGIN = 'https://market-signal-bot-sw7t.onrender.com'
KEY = 'k' * 48

def auth_url(**changes):
    args = dict(scope='mcp.read', state='test-state', redirect_uri=ORIGIN + '/ibkr/callback',
                code_challenge_method='S256', code_challenge='test-challenge')
    args.update(changes)
    return 'https://api.ibkr.com/oauth2/authorize?' + urlencode(args)

class InlineThread:
    def __init__(self, target, args, **kwargs):
        self.target, self.args = target, args
    def start(self):
        self.target(*self.args)

class HostedSetupTests(unittest.TestCase):
    def setUp(self):
        for item in [patch.dict('os.environ', IBKR_WEB_ORIGIN=ORIGIN, IBKR_WEB_SETUP_KEY=KEY),
                     patch.object(web, '_active', None),
                     patch.object(web, '_run', lambda c: c.set_redirect(auth_url()))]:
            item.start()
            self.addCleanup(item.stop)
        self.app = Flask(__name__)
        self.app.register_blueprint(web.bp)
        self.client = self.app.test_client()

    def begin(self):
        response = self.client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN, headers={'Origin': ORIGIN})
        self.assertEqual(response.status_code, 303)
        return web._active

    def test_configuration_key_and_origin(self):
        with patch.dict('os.environ', IBKR_WEB_SETUP_KEY=''):
            self.assertEqual(self.client.get('/ibkr/setup', base_url=ORIGIN).status_code, 503)
        self.assertEqual(self.client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN).status_code, 403)
        self.assertEqual(self.client.post('/ibkr/setup', data={'key':'wrong'}, base_url=ORIGIN, headers={'Origin': ORIGIN}).status_code, 403)
        self.assertEqual(self.client.get('/ibkr/setup/login', base_url=ORIGIN).status_code, 403)

    def test_cookie_and_redirect_headers(self):
        self.begin()
        cookie = self.client.get_cookie('__Host-hunter-setup', domain='market-signal-bot-sw7t.onrender.com')
        self.assertTrue(cookie.secure and cookie.http_only)
        self.assertEqual(cookie.same_site, 'Lax')
        r = self.client.get('/ibkr/setup/login', base_url=ORIGIN)
        self.assertEqual(r.location, auth_url())
        self.assertEqual(r.headers['Cache-Control'], 'no-store')
        self.assertEqual(r.headers['Referrer-Policy'], 'no-referrer')

    def test_callback_state_cookie_duplicate_and_replay(self):
        current = self.begin()
        for url in ['/ibkr/callback?code=c&state=wrong', '/ibkr/callback?code=a&code=b&state=test-state']:
            self.assertEqual(self.client.get(url, base_url=ORIGIN).status_code, 400)
        url = '/ibkr/callback?code=c&state=test-state'
        self.assertEqual(self.app.test_client().get(url, base_url=ORIGIN).status_code, 400)
        self.assertEqual(self.client.get(url, base_url=ORIGIN).status_code, 303)
        self.assertEqual(asyncio.run(current.wait()), ('c','test-state'))
        self.assertEqual(self.client.get(url, base_url=ORIGIN).status_code, 400)

    def test_oauth_destination_scope_and_pkce(self):
        for change in [dict(scope='mcp.read mcp.write'), dict(scope='mcp.orders.submit'), dict(redirect_uri='https://evil.example'), dict(state=''), dict(code_challenge_method='plain')]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                web.WebAuthorization(ORIGIN).set_redirect(auth_url(**change))
        with self.assertRaises(ValueError):
            web.WebAuthorization(ORIGIN).set_redirect(auth_url().replace('api.ibkr.com','evil.example'))

    def test_expiry_single_session_and_redaction(self):
        current = self.begin()
        response = self.client.get('/ibkr/setup/status', base_url=ORIGIN)
        self.assertNotIn(b'test-state', response.data)
        self.assertNotIn(KEY.encode(), response.data)
        self.assertEqual(self.client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN, headers={'Origin': ORIGIN}).status_code,409)
        current.created -= 181
        self.assertEqual(self.client.get('/ibkr/setup/login',base_url=ORIGIN).status_code,403)
        self.assertFalse(current.accept('c','test-state'))

    def test_sdk_callback_and_scope(self):
        from ibkr_mcp_client import oauth_provider, PrivateOAuthStorage
        async def receive(): return ('code','state')
        async def redirect(url): pass
        with tempfile.TemporaryDirectory() as directory:
            provider = oauth_provider(PrivateOAuthStorage(directory),redirect,receive,ORIGIN+'/ibkr/callback')
            meta = provider.context.client_metadata
            self.assertEqual(str(meta.redirect_uris[0]),ORIGIN+'/ibkr/callback')
            meta.scope = 'mcp.read mcp.orders.submit'
            self.assertEqual(meta.scope,'mcp.read')
