"""Rate-limited collector for Yahoo ^GSPC 1m bars. Research only; no orders, alerts or paid APIs.

Records request/receipt times per snapshot and the provider's own regularMarketTime. Builds complete
regular-session records in the schema of opening_validation_raw.json (day, step, csv) and NEVER
overwrites a stored session: the first complete read stays canonical, later differences are logged.
Classification is always DELAYED_RESEARCH_ONLY: Yahoo gives no verifiable delay or contract identity.
"""
import argparse
import gzip
import hashlib
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

from http_fetch import FetchFailed, ProviderFormatError, fetch_with_retry, validate_chart  # noqa: F401

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')
RIYADH = ZoneInfo('Asia/Riyadh')
CONSUMED_THROUGH = '2026-11-04'  # sessions up to here were used in earlier research
HOSTS = ('query1.finance.yahoo.com', 'query2.finance.yahoo.com')
SYMBOL = '^GSPC'
# Fixed universe of the frozen breadth screen (research/breadth_20261109/protocol.json). Order and members must not change.
BREADTH_SYMBOLS = ['^GSPC', 'NVDA', 'MSFT', 'AAPL', 'AMZN', 'GOOGL', 'META', 'AVGO', 'TSLA', 'BRK-B', 'JPM']
HERE = Path(__file__).resolve().parent


def utcnow():
    return datetime.now(timezone.utc)


def market_status(now):
    """Classify `now` with the XNYS calendar: PRE_OPEN / OPEN / POST_CLOSE on a session day,
    otherwise NO_SESSION with reason WEEKEND or HOLIDAY. Times are also given in Asia/Riyadh."""
    now = now.astimezone(timezone.utc)
    day = now.astimezone(NY).date()
    try:
        if not CAL.is_session(day.isoformat()):
            return {'state': 'NO_SESSION', 'reason': 'WEEKEND' if day.weekday() >= 5 else 'HOLIDAY', 'ny_date': day.isoformat()}
        opening = CAL.session_open(day.isoformat()).to_pydatetime()
        closing = CAL.session_close(day.isoformat()).to_pydatetime()
    except Exception as e:  # calendar range exhausted
        return {'state': 'UNKNOWN', 'reason': f'CALENDAR_ERROR:{e!r}', 'ny_date': day.isoformat()}
    state = 'PRE_OPEN' if now < opening else ('OPEN' if now < closing else 'POST_CLOSE')
    return {'state': state, 'ny_date': day.isoformat(), 'early_close': closing.astimezone(NY).hour < 16,
            'open_utc': opening.isoformat(), 'close_utc': closing.isoformat(),
            'open_riyadh': opening.astimezone(RIYADH).strftime('%H:%M'), 'close_riyadh': closing.astimezone(RIYADH).strftime('%H:%M')}


def fetch(host=HOSTS[0], interval='1m', rng='7d', timeout=20, symbol=SYMBOL):
    url = f'https://{host}/v8/finance/chart/{urllib.parse.quote(symbol, safe="")}?interval={interval}&range={rng}'
    body, info = fetch_with_retry(url, timeout=timeout)  # transient errors retried with backoff; failures raise
    return body, dict(info, host=host, url=url)


def parse(body):
    """Return (bars, meta). Bars are dicts with aware NY start time; null OHLC rows are dropped."""
    try:
        doc = json.loads(body)
    except ValueError as e:
        raise ProviderFormatError(f'format:not json ({e})') from e
    result = validate_chart(doc)  # specific error if the provider changed the response shape
    q = result['indicators']['quote'][0]
    meta = result['meta']
    bars, dropped = [], 0
    for i, t in enumerate(result['timestamp']):
        vals = [q[k][i] for k in ('open', 'high', 'low', 'close')]
        if any(v is None or not math.isfinite(v) or v <= 0 for v in vals):
            dropped += 1
            continue
        o, h, lo, c = vals
        if not lo <= min(o, c) <= max(o, c) <= h:
            dropped += 1
            continue
        bars.append({'at': datetime.fromtimestamp(t, timezone.utc).astimezone(NY), 'open': o, 'high': h,
                     'low': lo, 'close': c, 'volume': (q['volume'][i] or 0)})
    return bars, {'regular_market_time': datetime.fromtimestamp(meta['regularMarketTime'], timezone.utc).isoformat(),
                  'exchange_timezone': meta.get('exchangeTimezoneName'), 'granularity': meta.get('dataGranularity'),
                  'instrument_type': meta.get('instrumentType'), 'dropped_invalid_bars': dropped}


def completed_only(bars, received_at, minutes=1):
    """Drop a bar whose one-minute interval had not finished at receipt: it may still be forming."""
    return [b for b in bars if b['at'] + timedelta(minutes=minutes) <= received_at]


def build_sessions(bars, step=1):
    """Complete regular-grid sessions only (09:30..close-step). Incomplete days are reported, never filled."""
    by_day = {}
    for b in bars:
        by_day.setdefault(b['at'].date().isoformat(), {})[b['at']] = b
    sessions, incomplete = {}, []
    for day, got in sorted(by_day.items()):
        if not CAL.is_session(day):
            incomplete.append({'day': day, 'reason': 'not_an_XNYS_session'})
            continue
        opening = CAL.session_open(day).to_pydatetime().astimezone(NY)
        closing = CAL.session_close(day).to_pydatetime().astimezone(NY)
        grid = [opening+timedelta(minutes=i) for i in range(0, int((closing-opening).total_seconds()//60), step)]
        missing = [g for g in grid if g not in got]
        if missing:
            incomplete.append({'day': day, 'reason': 'incomplete_regular_grid', 'present': len(grid)-len(missing),
                               'expected': len(grid), 'first_missing': missing[0].strftime('%H:%M')})
            continue
        rows = ['time,open,high,low,close'] + [
            f"{g.strftime('%H:%M')},{got[g]['open']},{got[g]['high']},{got[g]['low']},{got[g]['close']}" for g in grid]
        sessions[day] = {'day': day, 'step': step, 'csv': '\n'.join(rows)+'\n',
                         'zero_volume_bars': sum(not got[g]['volume'] for g in grid),
                         'consumed_in_prior_research': day <= CONSUMED_THROUGH}
    return sessions, incomplete


def merge(store, sessions):
    """Insert unseen sessions; keep first read for existing ones and count differing re-reads."""
    added, revised = [], []
    for day, s in sessions.items():
        old = store.get(day)
        if old is None:
            store[day] = dict(s, first_seen_sha256=hashlib.sha256(s['csv'].encode()).hexdigest())
            added.append(day)
        elif old['csv'] != s['csv']:
            revised.append(day)
            old.setdefault('later_differing_reads', []).append(hashlib.sha256(s['csv'].encode()).hexdigest())
    return added, revised


def verify(store, first=None, last=None):
    """Independent coverage audit of a stored session file against the XNYS calendar (no market-hours dependence).

    Every calendar session between the first and last stored day must be present with the exact regular grid
    (including early closes), strictly increasing minute stamps, valid OHLC, and nothing outside the grid.
    """
    days = sorted(store)
    if not days:
        return {'ok': False, 'problems': ['empty_store'], 'complete_sessions': 0}
    first, last = first or days[0], last or days[-1]
    problems, complete = [], []
    for ts in CAL.sessions_in_range(first, last):
        day = str(ts.date())
        if day not in store:
            problems.append({'day': day, 'problem': 'session_missing_from_store'})
            continue
        opening = CAL.session_open(day).to_pydatetime().astimezone(NY)
        closing = CAL.session_close(day).to_pydatetime().astimezone(NY)
        step = store[day].get('step', 1)
        expected = [(opening+timedelta(minutes=i)).strftime('%H:%M') for i in range(0, int((closing-opening).total_seconds()//60), step)]
        rows = [r.split(',') for r in store[day]['csv'].strip().splitlines()[1:]]
        got = [r[0] for r in rows]
        # CSV columns are time,open,high,low,close: unpack explicitly for the OHLC check
        bad = [t for t, o, h, lo, c in rows if not (float(lo) > 0 and float(lo) <= min(float(o), float(c)) <= max(float(o), float(c)) <= float(h))]
        if got != expected:
            problems.append({'day': day, 'problem': 'grid_mismatch', 'rows': len(got), 'expected': len(expected)})
        elif bad:
            problems.append({'day': day, 'problem': 'invalid_ohlc', 'first': bad[0]})
        else:
            complete.append(day)
    extra = [d for d in days if d < first or d > last]
    return {'ok': not problems, 'range': [first, last], 'complete_sessions': len(complete), 'complete_days': complete,
            'problems': problems, 'outside_range': extra}


def seen_digests(outdir):
    path = outdir/'snapshots.jsonl'
    if not path.exists():
        return set()
    return {json.loads(l).get('raw_sha256') for l in path.read_text().splitlines() if l.strip()} - {None}


def write_new(path, data):
    """Create `path` exclusively: retained raw data is never overwritten (identical rewrite is a no-op)."""
    try:
        with path.open('xb') as f:
            f.write(data)
    except FileExistsError:
        if path.read_bytes() != data:
            raise RuntimeError(f'refusing to overwrite retained raw file {path.name}')


def run(body, fetch_meta, outdir):
    bars, pmeta = parse(body)
    received = datetime.fromisoformat(fetch_meta['received_at'])
    done = completed_only(bars, received)
    sessions, incomplete = build_sessions(done)
    digest = hashlib.sha256(body).hexdigest()
    last = done[-1]['at'] if done else None
    age = round((received-(last+timedelta(minutes=1))).total_seconds(), 1) if last else None
    status = market_status(received)
    if digest in seen_digests(outdir):  # identical provider payload already retained: write nothing
        return {'status': 'DUPLICATE_PAYLOAD_SKIPPED', 'raw_sha256': digest, 'received_at': fetch_meta['received_at'],
                'market_state_at_receipt': status, 'last_completed_bar_start_ny': last.isoformat() if last else None,
                'last_completed_bar_age_seconds': age}
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir/'raw').mkdir(exist_ok=True)
    stamp = received.strftime('%Y%m%dT%H%M%SZ')
    write_new(outdir/'raw'/f'{stamp}_GSPC_1m.json.gz', gzip.compress(body, mtime=0))
    path = outdir/'sessions.json'
    store = json.loads(path.read_text()) if path.exists() else {}
    added, revised = merge(store, sessions)
    path.write_text(json.dumps(store, indent=1, sort_keys=True)+'\n')
    snap = dict(fetch_meta, status='SNAPSHOT_STORED', provider=pmeta, symbol=SYMBOL, raw_sha256=digest, bars_received=len(bars),
                completed_bars=len(done), last_completed_bar_start_ny=last.isoformat() if last else None,
                last_completed_bar_age_seconds=age, market_state_at_receipt=status,
                sessions_added=added, sessions_revised_not_applied=revised, incomplete_days=incomplete,
                classification='DELAYED_RESEARCH_ONLY',
                classification_reason='Yahoo declares no delay and no contract identity; historical bars carry no per-bar receipt time. '
                                      'Receipt time here is the snapshot receipt only.')
    with (outdir/'snapshots.jsonl').open('a') as f:
        f.write(json.dumps(snap, sort_keys=True)+'\n')
    return snap


def run_breadth(fetched, outdir):
    """Store 5m bars for BREADTH_SYMBOLS under outdir/breadth5m. `fetched` is a list of (symbol, body, meta) or
    (symbol, None, {'error': ...}). Per (symbol, day) the first complete read is canonical; raw files are exclusive;
    an identical payload for a symbol is skipped. Days lacking any symbol are reported, never filled."""
    bdir = outdir/'breadth5m'
    (bdir/'raw').mkdir(parents=True, exist_ok=True)
    spath, snaps = bdir/'bars5m.json', bdir/'snapshots.jsonl'
    store = json.loads(spath.read_text()) if spath.exists() else {}
    seen = defaultdict(set)
    if snaps.exists():
        for line in snaps.read_text().splitlines():
            rec = json.loads(line)
            if rec.get('raw_sha256'):
                seen[rec['symbol']].add(rec['raw_sha256'])
    lines, failures, per_symbol = [], [], {}
    for symbol, body, meta in fetched:
        if body is None:
            failures.append(symbol)
            lines.append(dict(meta, symbol=symbol, status='FETCH_FAILED'))
            continue
        digest = hashlib.sha256(body).hexdigest()
        if digest in seen[symbol]:
            per_symbol[symbol] = 'DUPLICATE_PAYLOAD_SKIPPED'
            continue
        try:
            bars, pmeta = parse(body)
        except ValueError as e:
            failures.append(symbol)
            lines.append(dict(meta, symbol=symbol, status='PROVIDER_ERROR', error=repr(e)))
            continue
        received = datetime.fromisoformat(meta['received_at'])
        done = completed_only(bars, received, minutes=5)
        sessions, incomplete = build_sessions(done, step=5)
        stamp = received.strftime('%Y%m%dT%H%M%SZ')
        write_new(bdir/'raw'/f"{stamp}_{symbol.replace('^', '')}_5m.json.gz", gzip.compress(body, mtime=0))
        added, revised = merge(store.setdefault(symbol, {}), sessions)
        last = done[-1]['at'] if done else None
        per_symbol[symbol] = {'added': added, 'revised_not_applied': revised, 'incomplete': incomplete}
        lines.append(dict(meta, symbol=symbol, status='SNAPSHOT_STORED', provider=pmeta, raw_sha256=digest,
                          interval='5m', completed_bars=len(done), last_completed_bar_start_ny=last.isoformat() if last else None,
                          sessions_added=added, sessions_revised_not_applied=revised, incomplete_days=incomplete,
                          market_state_at_receipt=market_status(received), classification='DELAYED_RESEARCH_ONLY'))
    spath.write_text(json.dumps(store, indent=1, sort_keys=True)+'\n')
    with snaps.open('a') as f:
        for rec in lines:
            f.write(json.dumps(rec, sort_keys=True)+'\n')
    return {'failures': failures, 'per_symbol': per_symbol, 'coverage': verify_breadth(store)}


def verify_breadth(store):
    """Per-symbol calendar audit plus synchronization: a day is usable only if every symbol has its complete grid."""
    days = sorted({d for s in store.values() for d in s})
    if not days:
        return {'ok': False, 'problems': ['empty_store'], 'synchronized_days': []}
    sync, missing, problems = [], [], {}
    for symbol in BREADTH_SYMBOLS:
        rep_ = verify(store.get(symbol, {}), days[0], days[-1]) if store.get(symbol) else {'ok': False, 'problems': ['no_data']}
        if not rep_['ok']:
            problems[symbol] = rep_['problems']
    for ts in CAL.sessions_in_range(days[0], days[-1]):
        d = str(ts.date())
        lack = [s for s in BREADTH_SYMBOLS if d not in store.get(s, {})]
        (missing.append({'day': d, 'symbols': lack}) if lack else sync.append(d))
    return {'ok': not problems and not missing, 'range': [days[0], days[-1]], 'synchronized_days': sync,
            'missing': missing, 'per_symbol_problems': problems}


def collect_breadth(host, rng, pause=1.0):
    fetched = []
    for symbol in BREADTH_SYMBOLS:
        try:
            body, meta = fetch(host, '5m', rng, symbol=symbol)
            fetched.append((symbol, body, meta))
        except Exception as e:  # recorded per symbol; the run exits nonzero
            fetched.append((symbol, None, {'failed_at': utcnow().isoformat(), 'error': repr(e), 'attempts': getattr(e, 'attempts', None)}))
        time.sleep(pause)
    return fetched


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=HERE/'data', help='data directory (sessions.json, snapshots.jsonl, raw/)')
    p.add_argument('--host', default=HOSTS[0], choices=HOSTS)
    p.add_argument('--verify', action='store_true', help='audit the stored sessions only; no network')
    p.add_argument('--breadth', action='store_true', help='collect 5m bars for SPX and the ten breadth stocks')
    p.add_argument('--breadth-range', default='5d', choices=('5d', '1mo', '60d'))
    p.add_argument('--verify-breadth', action='store_true', help='audit breadth5m/bars5m.json only; no network')
    a = p.parse_args()
    if a.verify_breadth:
        report = verify_breadth(json.loads((a.out/'breadth5m'/'bars5m.json').read_text()))
        print(json.dumps(report, indent=1))
        sys.exit(0 if report['ok'] else 3)
    if a.breadth:
        res = run_breadth(collect_breadth(a.host, a.breadth_range), a.out)
        print(json.dumps({'failures': res['failures'], 'synchronized_days': res['coverage']['synchronized_days'],
                          'missing': res['coverage'].get('missing'), 'per_symbol': res['per_symbol']}, indent=1))
        sys.exit(2 if res['failures'] else 0)
    if a.verify:
        report = verify(json.loads((a.out/'sessions.json').read_text()))
        print(json.dumps(report, indent=1))
        sys.exit(0 if report['ok'] else 3)
    try:
        body, meta = fetch(a.host)
        snap = run(body, meta, a.out)
    except Exception as e:  # visible failure: record it, exit nonzero
        a.out.mkdir(parents=True, exist_ok=True)
        with (a.out/'snapshots.jsonl').open('a') as f:
            f.write(json.dumps({'failed_at': utcnow().isoformat(), 'error': repr(e), 'attempts': getattr(e, 'attempts', None)})+'\n')
        print('COLLECTION_FAILED', repr(e), file=sys.stderr)
        sys.exit(2)
    keys = ('status', 'received_at', 'http_seconds', 'completed_bars', 'last_completed_bar_start_ny',
            'last_completed_bar_age_seconds', 'market_state_at_receipt', 'sessions_added', 'incomplete_days', 'classification')
    print(json.dumps({k: snap[k] for k in keys if k in snap}, indent=1))
