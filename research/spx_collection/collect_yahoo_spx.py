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
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xc

NY = ZoneInfo('America/New_York')
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2026-12-31')
CONSUMED_THROUGH = '2026-11-04'  # sessions up to here were used in earlier research
HOSTS = ('query1.finance.yahoo.com', 'query2.finance.yahoo.com')
SYMBOL = '^GSPC'
HERE = Path(__file__).resolve().parent


def utcnow():
    return datetime.now(timezone.utc)


def fetch(host=HOSTS[0], interval='1m', rng='7d', timeout=20):
    url = f'https://{host}/v8/finance/chart/%5EGSPC?interval={interval}&range={rng}'
    requested = utcnow()
    t0 = time.monotonic()
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (research collector)'})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read()
        status = resp.status
    return body, {'host': host, 'url': url, 'status': status, 'requested_at': requested.isoformat(),
                  'received_at': utcnow().isoformat(), 'http_seconds': round(time.monotonic()-t0, 3)}


def parse(body):
    """Return (bars, meta). Bars are dicts with aware NY start time; null OHLC rows are dropped."""
    doc = json.loads(body)
    err = doc.get('chart', {}).get('error')
    result = (doc.get('chart', {}).get('result') or [None])[0]
    if err or not result:
        raise ValueError(f'provider_error:{err}')
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


def completed_only(bars, received_at):
    """Drop a bar whose one-minute interval had not finished at receipt: it may still be forming."""
    return [b for b in bars if b['at'] + timedelta(minutes=1) <= received_at]


def build_sessions(bars):
    """Complete regular-grid sessions only (09:30..close-1m). Incomplete days are reported, never filled."""
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
        grid = [opening+timedelta(minutes=i) for i in range(int((closing-opening).total_seconds()//60))]
        missing = [g for g in grid if g not in got]
        if missing:
            incomplete.append({'day': day, 'reason': 'incomplete_regular_grid', 'present': len(grid)-len(missing),
                               'expected': len(grid), 'first_missing': missing[0].strftime('%H:%M')})
            continue
        rows = ['time,open,high,low,close'] + [
            f"{g.strftime('%H:%M')},{got[g]['open']},{got[g]['high']},{got[g]['low']},{got[g]['close']}" for g in grid]
        sessions[day] = {'day': day, 'step': 1, 'csv': '\n'.join(rows)+'\n',
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
        expected = [(opening+timedelta(minutes=i)).strftime('%H:%M') for i in range(int((closing-opening).total_seconds()//60))]
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


def run(body, fetch_meta, outdir):
    bars, pmeta = parse(body)
    received = datetime.fromisoformat(fetch_meta['received_at'])
    done = completed_only(bars, received)
    sessions, incomplete = build_sessions(done)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir/'raw').mkdir(exist_ok=True)
    digest = hashlib.sha256(body).hexdigest()
    stamp = received.strftime('%Y%m%dT%H%M%SZ')
    (outdir/'raw'/f'{stamp}_GSPC_1m.json.gz').write_bytes(gzip.compress(body, mtime=0))
    path = outdir/'sessions.json'
    store = json.loads(path.read_text()) if path.exists() else {}
    added, revised = merge(store, sessions)
    path.write_text(json.dumps(store, indent=1, sort_keys=True)+'\n')
    last = done[-1]['at'] if done else None
    snap = dict(fetch_meta, provider=pmeta, symbol=SYMBOL, raw_sha256=digest, bars_received=len(bars),
                completed_bars=len(done), last_completed_bar_start_ny=last.isoformat() if last else None,
                last_completed_bar_age_seconds=(round((received-(last+timedelta(minutes=1))).total_seconds(), 1)
                                                 if last else None),
                sessions_added=added, sessions_revised_not_applied=revised, incomplete_days=incomplete,
                classification='DELAYED_RESEARCH_ONLY',
                classification_reason='Yahoo declares no delay and no contract identity; historical bars carry no per-bar receipt time. '
                                      'Receipt time here is the snapshot receipt only.')
    with (outdir/'snapshots.jsonl').open('a') as f:
        f.write(json.dumps(snap, sort_keys=True)+'\n')
    return snap


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, default=HERE/'data')
    p.add_argument('--host', default=HOSTS[0], choices=HOSTS)
    p.add_argument('--verify', action='store_true', help='audit the stored sessions only; no network')
    a = p.parse_args()
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
            f.write(json.dumps({'failed_at': utcnow().isoformat(), 'error': repr(e)})+'\n')
        print('COLLECTION_FAILED', repr(e), file=sys.stderr)
        sys.exit(2)
    print(json.dumps({k: snap[k] for k in ('received_at', 'http_seconds', 'completed_bars', 'last_completed_bar_start_ny',
                                            'sessions_added', 'incomplete_days', 'classification')}, indent=1))
