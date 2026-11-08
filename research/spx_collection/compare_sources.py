"""Compare Yahoo ^GSPC 1m sessions with the previously consumed input (1m) and the 5m frozen-forward archive.
Provenance check only: no detector, no outcomes, nothing tuned."""
import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def rows(csv_text):
    out = {}
    for line in csv_text.strip().splitlines()[1:]:
        t, o, h, lo, c = line.split(',')
        out[t] = (float(o), float(h), float(lo), float(c))
    return out


def compare(a, b):
    keys = sorted(set(a) & set(b))
    d = [abs(a[k][3]-b[k][3]) for k in keys]
    return {'bars_compared': len(keys), 'only_a': len(set(a)-set(b)), 'only_b': len(set(b)-set(a)),
            'close_equal_0.01': sum(x <= .01 for x in d), 'max_abs_close_diff': round(max(d), 4) if d else None,
            'median_abs_close_diff': round(sorted(d)[len(d)//2], 4) if d else None}


def agg5(r):
    keys = sorted(r)
    out = {}
    for i in range(0, len(keys), 5):
        g = keys[i:i+5]
        out[g[0]] = (r[g[0]][0], max(r[k][1] for k in g), min(r[k][2] for k in g), r[g[-1]][3])
    return out


if __name__ == '__main__':
    yahoo = json.loads((HERE/'data/sessions.json').read_text())
    consumed = {i['day']: i for i in json.loads(gzip.open(ROOT/'research/objective_review_20261107/opening_validation_raw.json.gz').read())}
    arch = json.loads(next((ROOT/'research/frozen_forward_20261103/v2/checkpoints').glob('*')).parent.joinpath(
        sorted(p.name for p in (ROOT/'research/frozen_forward_20261103/v2/checkpoints').iterdir())[-1], 'SPX_raw.json').read_text())
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    NY = ZoneInfo('America/New_York')
    a5 = {}
    for t, o, h, lo, c in zip(arch['time'], arch['open'], arch['high'], arch['low'], arch['close']):
        at = datetime.fromisoformat(t.replace('Z', '+00:00')).astimezone(NY)
        a5.setdefault(at.date().isoformat(), {})[at.strftime('%H:%M')] = (o, h, lo, c)
    report = {'note': 'provenance comparison only', 'vs_consumed_1m_input': {}, 'vs_archive_5m': {}}
    for day, s in sorted(yahoo.items()):
        y = rows(s['csv'])
        if day in consumed and consumed[day]['step'] == 1:
            report['vs_consumed_1m_input'][day] = compare(y, {k: v for k, v in rows(consumed[day]['csv']).items() if k < '16:00'})
        if day in a5 and len(a5[day]) == 78:
            report['vs_archive_5m'][day] = compare(agg5(y), a5[day])
    json.dump(report, sys.stdout, indent=1)
