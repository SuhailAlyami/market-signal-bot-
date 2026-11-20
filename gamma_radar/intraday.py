"""Intraday gamma radar log (silent forward test). Every ~15 min during the NYSE session: snapshot CBOE's delayed SPX
chain, compute the regime vs the flip level, and append one JSON line to <dir>/<NY date>.jsonl. Events recorded when
spot crosses the flip (into negative or positive gamma) or crosses one of the morning's negative-gamma levels since the
previous snapshot. Outcomes are scored later from the day's close; nothing is sent."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import exchange_calendars as xc

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import radar  # noqa: E402

NY = radar.NY
CAL = xc.get_calendar('XNYS', start='2026-01-01', end='2027-12-31')


def in_session(now):
    day = now.astimezone(NY).date().isoformat()
    if not CAL.is_session(day):
        return False
    return CAL.session_open(day).to_pydatetime() <= now <= CAL.session_close(day).to_pydatetime() + timedelta(minutes=20)


def events(prev, cur):
    """Crossings between two snapshots."""
    out = []
    if not prev or not cur.get('flip') or not prev.get('spot'):
        return out
    a, b, f = prev['spot'], cur['spot'], cur['flip']
    if a >= f > b:
        out.append({'type': 'into_negative_gamma', 'level': f})
    if a <= f < b:
        out.append({'type': 'into_positive_gamma', 'level': f})
    for lv in cur.get('levels') or []:
        k = lv['k']
        if lv['gex_bn'] < 0 and ((a > k >= b) or (a < k <= b)):
            out.append({'type': 'crossed_negative_level_down' if b < a else 'crossed_negative_level_up', 'level': k})
    return out


def run(out_dir, now=None, chain=None):
    now = now or datetime.now(timezone.utc)
    if not in_session(now):
        print('OUTSIDE_SESSION'); return None
    cur = radar.analyse(chain or radar.fetch(), now=now)
    cur['collected_utc'] = now.isoformat(timespec='seconds')
    path = os.path.join(out_dir, f"{now.astimezone(NY).date().isoformat()}.jsonl")
    prev = None
    if os.path.isfile(path):
        lines = [l for l in open(path).read().splitlines() if l.strip()]
        prev = json.loads(lines[-1]) if lines else None
    cur['events'] = events(prev, cur)
    os.makedirs(out_dir, exist_ok=True)
    with open(path, 'a') as f:
        f.write(json.dumps(cur)+'\n')
    print('SNAPSHOT', json.dumps({k: cur[k] for k in ('spot', 'flip', 'regime', 'events')}))
    return cur


if __name__ == '__main__':
    run(sys.argv[1] if len(sys.argv) > 1 else 'gamma-intraday')
