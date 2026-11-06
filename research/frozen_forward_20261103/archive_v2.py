"""Version 2: first-observed closed bars, revision ledger, atomic checkpoints.

Model, inputs, threshold and signal cooldown remain unchanged. This is an
explicit data-vintage policy change; the original strict runner is retained.
"""
import argparse, hashlib, json, math, os, shutil, tempfile
from pathlib import Path
import pandas as pd
from stable_archive import rows, merge_archive, FIELDS
from replay import replay

P = Path(__file__).resolve().parent
POLICY = 'v2_first_observed_closed_bars_with_revision_ledger'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def delivery_readiness(spx, es, asof):
    """Audit source latency independently of model events and historical scoring."""
    now = pd.Timestamp(asof)
    feeds = {}
    reasons = []
    closed_times = []
    for symbol, path in [('SPX', spx), ('ES', es)]:
        snapshot = json.loads(Path(path).read_text())
        closed, _ = rows(snapshot, now)
        times = set(closed)
        closed_times.append(times)
        latest = pd.Timestamp(max(times)) + pd.Timedelta(minutes=5) if times else None
        age = (now - latest).total_seconds() if latest is not None else None
        delay = snapshot.get('delayed')
        valid_delay = (type(delay) in (int, float) and math.isfinite(delay) and delay >= 0)
        feeds[symbol] = {
            'source': snapshot.get('source'),
            'declared_delay_seconds': delay if valid_delay else None,
            'last_closed_Riyadh': str(latest.tz_convert('Asia/Riyadh')) if latest is not None else None,
            'closed_bar_age_seconds': age,
        }
        if not valid_delay:
            reasons.append(symbol + '_PROVIDER_DELAY_UNKNOWN')
        elif delay > 180:
            reasons.append(symbol + '_PROVIDER_DELAY_EXCEEDS_180_SECONDS')
        if age is None or not 0 <= age <= 180:
            reasons.append(symbol + '_CLOSED_BAR_OUTSIDE_180_SECONDS')
    common = closed_times[0] & closed_times[1]
    latest_common = pd.Timestamp(max(common)) + pd.Timedelta(minutes=5) if common else None
    common_age = (now - latest_common).total_seconds() if latest_common is not None else None
    if common_age is None or not 0 <= common_age <= 180:
        reasons.append('COMMON_CLOSED_BAR_OUTSIDE_180_SECONDS')
    return {'provenance': 'RESEARCH_ONLY', 'maximum_age_seconds': 180,
            'eligible_for_fresh_signal_check': not reasons, 'reasons': reasons,
            'feeds': feeds,
            'latest_common_close_Riyadh': str(latest_common.tz_convert('Asia/Riyadh')) if latest_common is not None else None}

def merge_first(snapshot, archive, asof, ledger):
    incoming = json.loads(Path(snapshot).read_text())
    new, _ = rows(incoming, pd.Timestamp(asof))
    original = json.loads(archive.read_text())
    end = pd.to_datetime(original['time'], utc=True).max() + pd.Timedelta(minutes=5)
    old, _ = rows(original, end)
    revisions = []
    for t in sorted(old.keys() & new.keys()):
        changed = {k: {'first': old[t][k], 'incoming': new[t][k]}
                   for k in FIELDS if old[t][k] != new[t][k]}
        if changed:
            revisions.append({'bar_start_utc': t, 'changes': changed})
    # Keep the first closed observation for EVERY overlapping timestamp.
    # Strict merge still rejects missing-history insertion and invalid data.
    for i, ts in enumerate(pd.to_datetime(incoming['time'], utc=True)):
        t = str(ts)
        if t not in old:
            continue
        for k in FIELDS:
            if k in incoming:
                incoming[k][i] = old[t][k]
    filtered = archive.parent / (archive.stem + '_incoming.json')
    filtered.write_text(json.dumps(incoming))
    result = merge_archive(filtered, archive, asof)
    filtered.unlink()
    ledger.write_text(json.dumps({'policy': POLICY, 'asof_utc': str(asof),
        'snapshot_sha256': digest(Path(snapshot)), 'revision_count': len(revisions),
        'revisions': revisions}, indent=2))
    result.update(revision_policy=POLICY, revisions_logged=len(revisions))
    return result

def previous(root):
    pointer = root / 'CURRENT'
    if not pointer.exists():
        return None
    name = pointer.read_text().strip()
    if Path(name).name != name or name.startswith('.'):
        raise ValueError('invalid checkpoint pointer')
    folder = root / 'checkpoints' / name
    m = json.loads((folder / 'MANIFEST.json').read_text())
    if m['policy'] != POLICY:
        raise ValueError('checkpoint policy mismatch')
    for name, sha in m['sha256'].items():
        if Path(name).name != name or digest(folder / name) != sha:
            raise ValueError('checkpoint checksum mismatch')
    return folder

def run(spx, es, asof, root=None, evaluator=replay):
    asof = pd.Timestamp(asof)
    if asof.tzinfo is None:
        raise ValueError('asof timezone required')
    root = Path(root or P / 'v2')
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.run_lock'
    lock.mkdir()  # Concurrent writers fail closed.
    stage = None
    try:
        prior = previous(root)
        seed = prior or P
        (root / 'checkpoints').mkdir(exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.stage_', dir=root / 'checkpoints'))
        for name in ['SPX_archive.json', 'ES_archive.json', 'ARCHIVE_STATE.json']:
            shutil.copyfile(seed / name, stage / name)
        for name in ['GROK_SHADOW.json', 'OUTCOME_NOTIFICATIONS.json']:
            if (seed / name).exists():
                shutil.copyfile(seed / name, stage / name)
        audit = {'policy': POLICY, 'asof_Riyadh': str(asof.tz_convert('Asia/Riyadh')),
                 'previous_checkpoint': prior.name if prior else 'original_v1_seed'}
        for sym, source in [('SPX', spx), ('ES', es)]:
            source = Path(source)
            shutil.copyfile(source, stage / (sym + '_raw.json'))
            audit[sym] = merge_first(source, stage / (sym + '_archive.json'),
                                     asof, stage / (sym + '_REVISIONS.json'))
        report = evaluator(stage / 'SPX_archive.json', stage / 'ES_archive.json',
                           asof, stage / 'ARCHIVE_STATE.json', stage / 'ARCHIVE_RESULT.json')
        audit['delivery_readiness'] = delivery_readiness(spx, es, asof)
        (stage / 'ARCHIVE_AUDIT.json').write_text(json.dumps(audit, indent=2))
        m = {'policy': POLICY, 'sha256': {p.name: digest(p) for p in stage.iterdir() if p.is_file()}}
        (stage / 'MANIFEST.json').write_text(json.dumps(m, indent=2))
        name = asof.tz_convert('UTC').strftime('%Y%m%dT%H%M%S%fZ')
        final = root / 'checkpoints' / name
        os.rename(stage, final)
        stage = None
        tmp = root / 'CURRENT.tmp'
        tmp.write_text(name + '\n')
        os.replace(tmp, root / 'CURRENT')  # Atomic visibility of the ENTIRE pair + state.
        return {'checkpoint': str(final), 'archive': audit, 'reader': report}
    finally:
        if stage is not None:
            shutil.rmtree(stage)
        lock.rmdir()

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--spx', type=Path, required=True)
    p.add_argument('--es', type=Path, required=True)
    p.add_argument('--asof', default=pd.Timestamp.now(tz='UTC').isoformat())
    a = p.parse_args()
    print(json.dumps(run(a.spx, a.es, a.asof), indent=2))
