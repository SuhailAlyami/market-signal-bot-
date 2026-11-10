"""Offline tests for http_fetch: no network, injected opener/sleep/random."""
import io
import json
import socket
import unittest
import urllib.error

import http_fetch as h


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
    def read(self):
        return self.body
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def http_error(code, retry_after=None):
    hdrs = {'Retry-After': retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError('u', code, 'x', hdrs, io.BytesIO(b''))


def script(*steps):
    seq = list(steps)
    def opener(req, timeout):
        assert req.get_header('User-agent') == h.USER_AGENT  # one fixed, honest UA
        step = seq.pop(0)
        if isinstance(step, BaseException):
            raise step
        return step
    return opener


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def fetch(self, *steps, **kw):
        return h.fetch_with_retry('https://x', opener=script(*steps), sleep=self.sleeps.append, rand=lambda: 1.0, **kw)

    def test_success_first_try(self):
        body, info = self.fetch(Resp(b'ok'))
        self.assertEqual((body, info['status'], len(info['attempts']), self.sleeps), (b'ok', 200, 1, []))

    def test_timeout_then_success_with_exponential_backoff(self):
        body, info = self.fetch(socket.timeout('t'), urllib.error.URLError('reset'), Resp(b'ok'))
        self.assertEqual(body, b'ok')
        self.assertEqual(self.sleeps, [2.0, 4.0])
        self.assertEqual(len(info['attempts']), 3)

    def test_429_honours_retry_after_capped(self):
        self.fetch(http_error(429, '7'), http_error(503, '500'), Resp(b'ok'), max_delay=60)
        self.assertEqual(self.sleeps, [7.0, 60.0])

    def test_not_retried_for_403_404(self):
        for code in (403, 404):
            with self.assertRaises(h.FetchFailed) as cm:
                self.fetch(http_error(code))
            self.assertEqual(len(cm.exception.attempts), 1)
        self.assertEqual(self.sleeps, [])

    def test_gives_up_with_full_log(self):
        with self.assertRaises(h.FetchFailed) as cm:
            self.fetch(socket.timeout('a'), socket.timeout('b'), socket.timeout('c'), max_attempts=3)
        self.assertEqual(len(cm.exception.attempts), 3)
        self.assertEqual(self.sleeps, [2.0, 4.0])  # no sleep after the last attempt

    def test_empty_body_is_retried(self):
        body, _ = self.fetch(Resp(b''), Resp(b'ok'))
        self.assertEqual(body, b'ok')

    def test_full_jitter_bounds(self):
        self.assertEqual(h.backoff_delay(1, 2, 60, rand=lambda: 0.0), 0.0)
        self.assertEqual(h.backoff_delay(10, 2, 60, rand=lambda: 1.0), 60)


def chart(**over):
    doc = {'chart': {'error': None, 'result': [{'meta': {'regularMarketTime': 1}, 'timestamp': [1, 2],
           'indicators': {'quote': [{'open': [1, 1], 'high': [2, 2], 'low': [.5, .5], 'close': [1, 1], 'volume': [0, 0]}]}}]}}
    r = doc['chart']['result'][0]
    for k, v in over.items():
        if k == 'drop':
            path, key = v
            (r if path == 'r' else r['indicators']['quote'][0] if path == 'q' else r['meta']).pop(key)
        if k == 'short_close':
            r['indicators']['quote'][0]['close'] = [1]
    return doc


class FormatTests(unittest.TestCase):
    def test_valid(self):
        self.assertIn('timestamp', h.validate_chart(chart()))

    def test_specific_reasons_for_shape_changes(self):
        cases = {('r', 'indicators'): 'missing indicators', ('q', 'volume'): 'missing quote.volume',
                 ('m', 'regularMarketTime'): 'missing meta.regularMarketTime'}
        for drop, msg in cases.items():
            with self.assertRaisesRegex(h.ProviderFormatError, msg):
                h.validate_chart(chart(drop=drop))
        with self.assertRaisesRegex(h.ProviderFormatError, 'length mismatch quote.close'):
            h.validate_chart(chart(short_close=True))
        with self.assertRaisesRegex(h.ProviderFormatError, 'provider_error'):
            h.validate_chart({'chart': {'error': {'code': 'Not Found'}, 'result': None}})

    def test_collector_parse_reports_format_change(self):
        import collect_yahoo_spx as c
        with self.assertRaisesRegex(h.ProviderFormatError, 'not json'):
            c.parse(b'<html>blocked</html>')
        with self.assertRaisesRegex(h.ProviderFormatError, 'missing indicators'):
            c.parse(json.dumps(chart(drop=('r', 'indicators'))).encode())


if __name__ == '__main__':
    unittest.main()
