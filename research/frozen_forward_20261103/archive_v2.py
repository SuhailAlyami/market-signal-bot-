"""Version 2: first-observed closed bars, revision ledger, atomic checkpoints.

Model, inputs, threshold and signal cooldown remain unchanged. This is an
explicit data-vintage policy change; the original strict runner is retained.
"""
import argparse, hashlib, json, os, shutil, tempfile
from pathlib import Path
import pandas as pd
from stable_archive import rows, merge_archive, FIELDS
from replay import replay

P = Path(__file__).resolve().parent
POLICY = 'v2_first_observed_closed_bars_with_revision_ledger'

def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

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
        audit = {'policy': POLICY, 'asof_Riyadh': str(asof.tz_convert('Asia/Riyadh')),
                 'previous_checkpoint': prior.name if prior else 'original_v1_seed'}
        for sym, source in [('SPX', spx), ('ES', es)]:
            source = Path(source)
            shutil.copyfile(source, stage / (sym + '_raw.json'))
            audit[sym] = merge_first(source, stage / (sym + '_archive.json'),
                                     asof, stage / (sym + '_REVISIONS.json'))
        report = evaluator(stage / 'SPX_archive.json', stage / 'ES_archive.json',
                           asof, stage / 'ARCHIVE_STATE.json', stage / 'ARCHIVE_RESULT.json')
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
