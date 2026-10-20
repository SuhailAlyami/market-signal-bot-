"""Single-writer, append-only completed-bar evidence with actual receipt times.

Only contract identity and market bars are persisted; never OAuth or account
responses. Revisions retain the earlier version so later tests can reconstruct
what was known at a particular time. Retention requires persistent storage.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

import pandas as pd
from premium_radar import history_frame


def archive_history(directory, identity, raw, received_at):
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise ValueError('aware_receipt_required')
    contract_id = identity['contract_id']
    if type(contract_id) is not int or contract_id <= 0:
        raise ValueError('invalid_contract_id')
    data = history_frame(raw)
    data = data[data.index + pd.Timedelta(minutes=1) <= received_at]
    directory = Path(directory) / 'premium_bars'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    pending = {}
    for start, row in data.iterrows():
        bar = {key.lower(): float(row[key]) for key in ('Open', 'High', 'Low', 'Close', 'Volume')}
        if not all(math.isfinite(value) for value in bar.values()):
            raise ValueError('nonfinite_archive_bar')
        payload = {'contract_id': contract_id, 'bar_start': start.isoformat(), **bar}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()
        record = {**payload, 'version_sha256': digest,
                  'received_at': received_at.astimezone(timezone.utc).isoformat(),
                  'feed_status': identity['feed_status'], 'historical_delayed': raw.get('delayed'),
                  'source': 'IBKR option last-trade OHLCV', 'bar_seconds': 60,
                  'exchange': identity['exchange'], 'expiry': identity['expiry'],
                  'side': identity['side'], 'strike': float(identity['strike'])}
        path = directory / f'{contract_id}-{start.date().isoformat()}.jsonl'
        pending.setdefault(path, []).append(record)
    added = 0
    for path, records in pending.items():
        seen = set()
        if path.exists():
            # Corruption must not erase provenance or reset deduplication.
            for line in path.read_text().splitlines():
                old = json.loads(line)
                seen.add(old['version_sha256'])
        fresh = [record for record in records if record['version_sha256'] not in seen]
        if not fresh:
            continue
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'a', encoding='utf-8') as stream:
            for record in fresh:
                stream.write(json.dumps(record, allow_nan=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        added += len(fresh)
    return added
