"""One preregistered readiness stage, separate from the existing recross trigger."""
import argparse
import json
from pathlib import Path

import pandas as pd

from evaluate_spx_sessions import (
    PROTOCOL_COMMIT as ORIGINAL_PROTOCOL, evaluate_partition, load_capture, quality_gate,
)
from research_spx_premove import signal_schedule

PROTOCOL_COMMIT = 'f88f5d6a7988fe04ec46fb9a4444cbbf1430604e'
MODEL = 'pullback_preparation_v1'
VALIDATION = ['2026-08-11', '2026-08-12', '2026-08-13', '2026-08-14']
BASELINES = ('pullback_release', 'original_candidate', 'no_signal')


def readiness(f):
    side = pd.Series(0, index=f.index, dtype=int)
    up = ((f.ema5 > f.ema15) & (f.move15 > 0) &
          (f.previous_close <= f.previous_ema5) &
          (f.close <= f.ema5) & (f.body > 0))
    down = ((f.ema5 < f.ema15) & (f.move15 < 0) &
            (f.previous_close >= f.previous_ema5) &
            (f.close >= f.ema5) & (f.body < 0))
    side.loc[up], side.loc[down] = 1, -1
    return side.where(f.valid, 0)


def schedule(f, model):
    if model != MODEL:
        return signal_schedule(f, model)
    signals, until = [], None
    for index, (time, side) in enumerate(readiness(f).items()):
        decision = time + pd.Timedelta(minutes=1)
        if side and (until is None or decision >= until):
            signals.append(dict(index=index, direction=int(side), detected_at=decision.isoformat()))
            until = decision + pd.Timedelta(minutes=10)
    return signals


def run_validation(capture, previous_study, output, registry):
    # Reserve before calculations, so interrupted outcomes cannot appear untouched.
    with Path(output).open('x', encoding='utf-8') as stream:
        result = dict(protocol_commit=PROTOCOL_COMMIT, model_selected=MODEL,
                      readiness='NOT_READY', accepted=False, holdout_opened=False,
                      reason='IN_PROGRESS', notifications_enabled=False, orders_enabled=False)
        json.dump(result, stream)
        stream.flush()
        old = json.loads(Path(previous_study).read_text(encoding='utf-8'))
        if old.get('holdout_opened') is not False or old['splits']['holdout'] != VALIDATION:
            raise ValueError('validation_not_previously_unopened')
        if any((Path(registry) / ORIGINAL_PROTOCOL / f'{day}.json').exists() for day in VALIDATION):
            raise ValueError('previous_holdout_already_reserved')
        dataset, inventory, digest = load_capture(capture)
        if digest != old['manifest_sha256'] or sorted(dataset)[-4:] != VALIDATION:
            raise ValueError('preregistered_capture_mismatch')
        result.update(manifest_sha256=digest, source='IBKR_TWS_API_HISTORY',
                      live_feed_verified=False, inventory=inventory,
                      consumed_development_days=sorted(dataset)[:-4],
                      validation_days=VALIDATION,
                      conditional_holdout_days=['2026-08-17', '2026-08-18', '2026-08-19', '2026-08-20'],
                      parameter_search=False)
        reservation = Path(registry) / PROTOCOL_COMMIT
        reservation.mkdir(parents=True, exist_ok=True)
        for day in VALIDATION:
            with (reservation / f'validation-{day}.json').open('x', encoding='utf-8') as record:
                json.dump(dict(protocol_commit=PROTOCOL_COMMIT, stage='validation',
                               day=day, manifest_sha256=digest,
                               status='CONSUMED_OR_RESERVED_DO_NOT_REUSE'), record)
        result['validation'] = evaluate_partition(dataset, VALIDATION, (MODEL, *BASELINES), scheduler=schedule)
        result['validation_gate'] = quality_gate(result['validation']['models'][MODEL]['strict']['0'])
        result['reason'] = ('validation_pass_requires_unacquired_conditional_holdout'
                            if result['validation_gate']['passed']
                            else 'validation_failed_new_holdout_not_acquired')
        result['limitations'] = ['Fixed hypothesis, no training/validation parameter search.',
                                'Earlier 16 sessions are consumed development, not independent.',
                                'Historical bars do not prove live latency, option P&L or production readiness.',
                                'Auxiliary pre-anchor matching does not decide acceptance.']
        stream.seek(0)
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.truncate()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--previous-study', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--registry', default='.hunter-state/spx-holdout-locks')
    args = parser.parse_args()
    result = run_validation(args.capture, args.previous_study, args.output, args.registry)
    print(json.dumps({key: result[key] for key in ('readiness', 'reason', 'holdout_opened', 'validation_gate')}))
    raise SystemExit(0 if result['validation_gate']['passed'] else 1)


if __name__ == '__main__':
    main()
