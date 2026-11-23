import io
import json
import os
import sys
import unittest
import urllib.error
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notify_chain as C
import daily_range as D

GH = {'GITHUB_TOKEN': 't', 'GITHUB_REPOSITORY': 'o/r'}
SMTP = {'SMTP_HOST': 'smtp.x', 'SMTP_USER': 'u@x', 'SMTP_PASSWORD': 'p', 'NOTIFY_EMAIL_TO': 'me@x'}


class Resp:
    def __init__(self, obj): self.obj = obj
    def read(self): return json.dumps(self.obj).encode()


class FakeSMTP:
    sent = []
    def __init__(self, host, port, timeout): self.host, self.port = host, port
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def starttls(self, context): pass
    def login(self, u, p): pass
    def send_message(self, m): FakeSMTP.sent.append(m)


class ChainTests(unittest.TestCase):
    def test_github_issue_posts_title_and_body(self):
        seen = {}
        def opener(req, timeout):
            seen['url'], seen['data'] = req.full_url, json.loads(req.data)
            return Resp({'number': 7})
        self.assertTrue(C.github_issue('سطر أول\nتفاصيل', env=GH, opener=opener))
        self.assertEqual(seen['url'], 'https://api.github.com/repos/o/r/issues')
        self.assertIn('سطر أول', seen['data']['title'])
        self.assertIn('تفاصيل', seen['data']['body'])

    def test_github_skipped_or_failed_returns_false(self):
        self.assertFalse(C.github_issue('x', env={}))
        def boom(req, timeout): raise urllib.error.HTTPError('u', 403, 'no', {}, io.BytesIO(b''))
        self.assertFalse(C.github_issue('x', env=GH, opener=boom))

    def test_email_needs_all_secrets_then_sends(self):
        self.assertFalse(C.email('x', env={'SMTP_HOST': 'h'}))
        FakeSMTP.sent = []
        self.assertTrue(C.email('hello', env=SMTP, smtp_factory=FakeSMTP))
        self.assertEqual(FakeSMTP.sent[0]['To'], 'me@x')

    def test_chain_stops_at_first_success(self):
        calls = []
        a = lambda t: calls.append('a') or False
        b = lambda t: calls.append('b') or True
        c = lambda t: calls.append('c') or True
        b.__name__ = 'b'
        with mock.patch.object(C, 'FALLBACKS', (a, b, c)):
            self.assertEqual(C.fallback('x'), 'b')
        self.assertEqual(calls, ['a', 'b'])


class SendOrderTests(unittest.TestCase):
    def setUp(self):
        self._env = {k: os.environ.pop(k, None) for k in ['TELEGRAM_NOTIFY', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID']}
    def tearDown(self):
        for k, v in self._env.items():
            if v is not None: os.environ[k] = v

    def test_telegram_ok_never_touches_fallback(self):
        with mock.patch.object(D, '_telegram', return_value=True), \
             mock.patch.object(C, 'fallback', side_effect=AssertionError('must not run')):
            self.assertTrue(D.send('x'))

    def test_telegram_down_falls_back_and_marks_delivered(self):
        with mock.patch.object(D, '_telegram', return_value=False), \
             mock.patch.object(C, 'fallback', return_value='github_issue'), \
             mock.patch('sys.stdout', new_callable=io.StringIO) as out:
            self.assertTrue(D.send('x'))
        self.assertIn('TELEGRAM_OK_FALLBACK', out.getvalue())

    def test_all_channels_down_returns_false(self):
        with mock.patch.object(D, '_telegram', return_value=False), \
             mock.patch.object(C, 'fallback', return_value=None):
            self.assertFalse(D.send('x'))


if __name__ == '__main__':
    unittest.main()
