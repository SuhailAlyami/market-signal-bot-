"""Input loading and date selection for the frozen breadth screen. No signal, agreement or scoring logic here."""
import gzip
import json
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from breadth_core import UNIVERSE  # noqa: F401  (fixed universe from protocol.json)
from objective_review import NY, load_sessions

HERE = Path(__file__).resolve().parent
HOLDOUT_FROM = '2026-11-05'
SYMBOLS = ['^GSPC']+UNIVERSE


def _sessions_from_rows(by_day):
    items = [{'day': d, 'step': 5, 'csv': 'time,open,high,low,close\n'+'\n'.join(rows)+'\n'} for d, rows in by_day.items()]
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump(items, f)
    return load_sessions(Path(f.name))


# --- development input: the 60-day snapshot fetched 2026-11-09, dates < HOLDOUT_FROM (unchanged from original run.py)
def bars_of(symbol):
    r = json.loads(gzip.open(HERE/'raw'/f"{symbol.replace('^', '')}_5m_60d.json.gz").read())['chart']['result'][0]
    q = r['indicators']['quote'][0]
    out = {}
    for i, t in enumerate(r['timestamp']):
        at = datetime.fromtimestamp(t, timezone.utc).astimezone(NY)
        vals = [q[k][i] for k in ('open', 'high', 'low', 'close')]
        if at.date().isoformat() < HOLDOUT_FROM and all(v is not None for v in vals):
            out[at] = vals
    return out


def dev_inputs():
    spx = bars_of('^GSPC')
    by = defaultdict(list)
    for at, v in sorted(spx.items()):
        by[at.date().isoformat()].append(f"{at.strftime('%H:%M')},{v[0]},{v[1]},{v[2]},{v[3]}")
    sessions, excluded = _sessions_from_rows(by)
    closes = {s: {at: v[3] for at, v in bars_of(s).items()} for s in UNIVERSE}
    return sessions, excluded, closes


# --- forward input: the collector's synchronized 5m store (data branch breadth5m/bars5m.json)
def forward_inputs(store_path, start=HOLDOUT_FROM, end=None, allow_consumed=False):
    """Only days where ALL 11 symbols have a complete stored session are used; other days are excluded with reason.

    Dates before HOLDOUT_FROM are refused unless allow_consumed=True (used only for equivalence tests on consumed dates).
    """
    if start < HOLDOUT_FROM and not allow_consumed:
        raise ValueError('forward input must start on or after ' + HOLDOUT_FROM)
    store = json.loads(Path(store_path).read_text())
    days = sorted({d for s in SYMBOLS for d in store.get(s, {}) if d >= start and (end is None or d <= end)})
    use, skipped = [], []
    for d in days:
        missing = [s for s in SYMBOLS if d not in store.get(s, {})]
        (skipped.append({'day': d, 'reason': 'missing_symbols', 'symbols': missing}) if missing else use.append(d))
    by = {d: store['^GSPC'][d]['csv'].strip().splitlines()[1:] for d in use}
    sessions, excluded = _sessions_from_rows(by) if use else ([], [])
    closes = {u: {} for u in UNIVERSE}
    for u in UNIVERSE:
        for d in use:
            for line in store[u][d]['csv'].strip().splitlines()[1:]:
                t, _o, _h, _l, c = line.split(',')
                closes[u][datetime.fromisoformat(f'{d}T{t}').replace(tzinfo=NY)] = float(c)
    return sessions, excluded+skipped, closes
