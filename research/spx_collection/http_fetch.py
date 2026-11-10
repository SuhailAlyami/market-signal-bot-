"""Polite, resilient HTTP fetch for the research collector.

- Retries only transient failures: timeouts, connection errors, HTTP 429 and 5xx.
- Exponential backoff with full jitter, capped; honours a numeric Retry-After header.
- Never retries other 4xx (e.g. 403/404): those mean "not allowed / not found", not "try harder".
- One fixed, honest User-Agent. No User-Agent rotation or other measures to evade provider limits.
- Every attempt is logged so a failure is visible in the snapshot record, never silent.
"""
import random
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

USER_AGENT = 'Mozilla/5.0 (compatible; suhail-hunter-research-collector)'
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchFailed(Exception):
    """Raised after the last attempt; carries the per-attempt log."""

    def __init__(self, message, attempts):
        super().__init__(message)
        self.attempts = attempts


def backoff_delay(attempt, base, cap, rand=random.random):
    """Full-jitter exponential backoff: uniform in [0, min(cap, base * 2**(attempt-1))]."""
    return rand()*min(cap, base*2**(attempt-1))


def _retry_after(err):
    value = err.headers.get('Retry-After') if getattr(err, 'headers', None) else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except ValueError:
        return None  # HTTP-date form is ignored; normal backoff applies


def fetch_with_retry(url, timeout=20, max_attempts=4, base_delay=2.0, max_delay=60.0,
                     opener=urllib.request.urlopen, sleep=time.sleep, rand=random.random, now=lambda: datetime.now(timezone.utc)):
    """Return (body, info). info has status, attempts log, first/last request and receipt times."""
    log = []
    for attempt in range(1, max_attempts+1):
        requested = now()
        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
            with opener(req, timeout=timeout) as resp:
                body, status = resp.read(), resp.status
            if not body:
                raise urllib.error.URLError('empty response body')
            log.append({'attempt': attempt, 'requested_at': requested.isoformat(), 'status': status})
            return body, {'status': status, 'attempts': log, 'first_requested_at': log[0]['requested_at'],
                          'requested_at': requested.isoformat(), 'received_at': now().isoformat(),
                          'http_seconds': round(time.monotonic()-t0, 3)}
        except urllib.error.HTTPError as e:
            entry = {'attempt': attempt, 'requested_at': requested.isoformat(), 'status': e.code, 'error': f'HTTP {e.code}'}
            log.append(entry)
            if e.code not in RETRY_STATUS:
                raise FetchFailed(f'HTTP {e.code} (not retried)', log) from e
            wait = _retry_after(e)
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            log.append({'attempt': attempt, 'requested_at': requested.isoformat(), 'error': repr(e)})
            wait = None
        if attempt == max_attempts:
            break
        delay = min(max_delay, wait) if wait is not None else backoff_delay(attempt, base_delay, max_delay, rand)
        log[-1]['sleep_seconds'] = round(delay, 3)
        sleep(delay)
    raise FetchFailed(f'gave up after {max_attempts} attempts: {log[-1].get("error")}', log)


class ProviderFormatError(ValueError):
    """The provider response no longer has the expected structure (schema/format change)."""


def validate_chart(doc):
    """Fail fast with a specific reason if the Yahoo chart JSON changed shape."""
    if not isinstance(doc, dict) or 'chart' not in doc:
        raise ProviderFormatError('format:missing chart')
    chart = doc['chart']
    if chart.get('error'):
        raise ProviderFormatError(f"provider_error:{chart['error']}")
    result = chart.get('result')
    if not result or not isinstance(result, list):
        raise ProviderFormatError('format:missing result')
    r = result[0]
    for key in ('meta', 'timestamp', 'indicators'):
        if key not in r:
            raise ProviderFormatError(f'format:missing {key}')
    quotes = r['indicators'].get('quote')
    if not quotes or not isinstance(quotes, list):
        raise ProviderFormatError('format:missing indicators.quote')
    q = quotes[0]
    n = len(r['timestamp'])
    for key in ('open', 'high', 'low', 'close', 'volume'):
        if key not in q:
            raise ProviderFormatError(f'format:missing quote.{key}')
        if len(q[key]) != n:
            raise ProviderFormatError(f'format:length mismatch quote.{key} {len(q[key])} != timestamp {n}')
    if 'regularMarketTime' not in r['meta']:
        raise ProviderFormatError('format:missing meta.regularMarketTime')
    if any(not isinstance(t, int) for t in r['timestamp']):
        raise ProviderFormatError('format:non-integer timestamp')
    return r
