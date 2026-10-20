"""Replay a code-hash-frozen local option-premium hypothesis on separate inputs."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
from premium_local_research import aggregate, load


def replicate(frozen, paths):
    actual_hash = hashlib.sha256(Path(__file__).with_name('premium_local_research.py').read_bytes()).hexdigest()
    if actual_hash != frozen['source_code_sha256']:
        raise ValueError('frozen_code_changed')
    if not frozen['selected']:
        raise ValueError('no_candidate_selected')
    sources = load(paths)
    used = set(frozen['train_sha256']+frozen['validation_sha256'])
    if any(sha in used for sha,_,_ in sources):
        raise ValueError('development_reused_as_replication')
    cutoff = pd.Timestamp(frozen['replication_cutoff_utc'])
    trimmed = [(sha, data.loc[data.index<=cutoff], prepared[:int((data.index<=cutoff).sum())])
               for sha,data,prepared in sources]
    return {'status':'NOT_READY','frozen_at':frozen['frozen_at'], 'config':frozen['selected']['config'],
            'evaluation_amendment':frozen.get('evaluation_amendment'),
            'original_freeze_commit':frozen.get('original_freeze_commit'),
            'independent_untouched_holdout':False,
            'source_code_sha256':actual_hash, 'cutoff_utc':str(cutoff),
            'delays':{str(delay):aggregate(trimmed,frozen['selected']['config'],delay)
                      for delay in frozen['replication_delays_seconds']},
            'limitations':['Related strikes on the same market dates are correlated replication, not independent sessions.',
                           'Selected expiry had changing DTE; this is not a historical 0DTE-only sample.',
                           'Historical trade highs are not executable books, fills, or profit.',
                           'Added latency is an assumption; source publication times are absent.'],
            'notifications_enabled':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--frozen',required=True)
    parser.add_argument('--inputs',nargs='+',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    report=replicate(json.loads(Path(args.frozen).read_text()),args.inputs)
    Path(args.output).write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'config':report['config'],'results':{key:value['methods'] for key,value in report['delays'].items()}},indent=2))
