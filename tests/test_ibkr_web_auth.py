import asyncio
from urllib.parse import urlencode

import pytest
from flask import Flask
import ibkr_web_auth as module

ORIGIN = 'https://market-signal-bot-sw7t.onrender.com'
KEY = 'k' * 48


def auth_url(**changes):
    args = dict(scope='mcp.read', state='valid-state', redirect_uri=ORIGIN + '/ibkr/callback',
                code_challenge_method='S256', code_challenge='test-challenge')
    args.update(changes)
    return 'https://api.ibkr.com/oauth2/authorize?' + urlencode(args)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('IBKR_WEB_ORIGIN', ORIGIN)
    monkeypatch.setenv('IBKR_WEB_SETUP_KEY', KEY)
    monkeypatch.setattr(module, '_active', None)
    monkeypatch.setattr(module, '_run', lambda current: current.set_redirect(auth_url()))
    app = Flask(__name__)
    app.register_blueprint(module.bp)
    return app.test_client()


def begin(client):
    response = client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN,
                           headers={'Origin': ORIGIN})
    assert response.status_code == 303
    return module._active


def test_no_configuration_fails_closed(client, monkeypatch):
    monkeypatch.delenv('IBKR_WEB_SETUP_KEY')
    assert client.get('/ibkr/setup', base_url=ORIGIN).status_code == 503


def test_authentication_and_csrf(client):
    assert client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN).status_code == 403
    assert client.post('/ibkr/setup', data={'key': 'wrong'}, base_url=ORIGIN,
                       headers={'Origin': ORIGIN}).status_code == 403
    assert client.get('/ibkr/setup/login', base_url=ORIGIN).status_code == 403


def test_cookie_and_login_are_owner_gated(client):
    begin(client)
    cookie = client.get_cookie('__Host-hunter-setup', domain='market-signal-bot-sw7t.onrender.com')
    assert cookie.secure and cookie.http_only and cookie.same_site == 'Lax'
    response = client.get('/ibkr/setup/login', base_url=ORIGIN)
    assert response.status_code == 303
    assert response.location == auth_url()
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['Referrer-Policy'] == 'no-referrer'


def test_callback_wrong_state_no_cookie_duplicates_replay(client):
    current = begin(client)
    assert client.get('/ibkr/callback?code=c&state=wrong', base_url=ORIGIN).status_code == 400
    assert client.get('/ibkr/callback?code=a&code=b&state=valid-state', base_url=ORIGIN).status_code == 400
    outsider = client.application.test_client()
    assert outsider.get('/ibkr/callback?code=c&state=valid-state', base_url=ORIGIN).status_code == 400
    response = client.get('/ibkr/callback?code=c&state=valid-state', base_url=ORIGIN)
    assert response.status_code == 303
    assert asyncio.run(current.wait()) == ('c', 'valid-state')
    assert client.get('/ibkr/callback?code=c&state=valid-state', base_url=ORIGIN).status_code == 400


@pytest.mark.parametrize('changes', [dict(scope='mcp.read mcp.write'), dict(scope='mcp.orders.submit'),
                                     dict(redirect_uri='https://evil.example/callback'),
                                     dict(code_challenge_method='plain'), dict(state='')])
def test_rejects_broader_scope_and_invalid_oauth(changes):
    current = module.WebAuthorization(ORIGIN)
    with pytest.raises(ValueError):
        current.set_redirect(auth_url(**changes))


def test_rejects_untrusted_authorization_host():
    current = module.WebAuthorization(ORIGIN)
    with pytest.raises(ValueError):
        current.set_redirect(auth_url().replace('api.ibkr.com', 'evil.example'))


def test_expiration_and_simultaneous_setup(client):
    current = begin(client)
    assert client.post('/ibkr/setup', data={'key': KEY}, base_url=ORIGIN,
                       headers={'Origin': ORIGIN}).status_code == 409
    current.created -= 181
    assert client.get('/ibkr/setup/login', base_url=ORIGIN).status_code == 403
    assert not current.accept('c', 'valid-state')


def test_health_status_never_contains_sensitive_oauth(client):
    begin(client)
    response = client.get('/ibkr/setup/status', base_url=ORIGIN)
    assert response.status_code == 200
    assert b'valid-state' not in response.data
    assert KEY.encode() not in response.data


def test_sdk_metadata_keeps_read_scope_for_hosted_callback(tmp_path):
    from ibkr_mcp_client import oauth_provider, PrivateOAuthStorage
    async def receive():
        return ('code', 'state')
    async def redirect(url):
        pass
    provider = oauth_provider(PrivateOAuthStorage(tmp_path), redirect, receive,
                              ORIGIN + '/ibkr/callback')
    metadata = provider.context.client_metadata
    assert str(metadata.redirect_uris[0]) == ORIGIN + '/ibkr/callback'
    metadata.scope = 'mcp.read mcp.orders.submit'
    assert metadata.scope == 'mcp.read'
