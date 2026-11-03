"""Reproduce the frozen book, audit leakage, then test one pre-registered veto.

Development (bar index < 400) motivates the veto. The locked comparison is the
original selective five-minute price signal log and is not used to change the
rule after it is scored. November 3 forward outcomes are descriptive only.
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from close_policy import adopt_filter, continuation, wilson

HERE = Path(__file__).resolve().parent
RESEARCH = HERE.parent
UNI = RESEARCH / 'multiframe_unified_20261103'
WF = RESEARCH / 'multiframe_walkforward_20261103'
FWD = RESEARCH / 'frozen_forward_20261103'
sys.path.insert(0, str(UNI))
import run as base  # noqa: E402

FROZEN_SHA = 'fb281774690ab5848d26c16f6583cfb632a80bcdc12ea486160a0a3f97850f6b'
LOCKED_INDEX = 400
HORIZON = 6


def load():
    d, es = base.prepare(
        base.raw(UNI / 'raw' / 'SPX_FIVE_MINS.json'),
        base.raw(UNI / 'raw' / 'ES_FIVE_MINS.json'),
        5,
    )
    technical = base.ft.technical(d, es)
    patterns = base.ft.patterns(d)
    features = pd.concat([technical, patterns], axis=1)
    return d, es, features


def outcomes(d):
    n = len(d)
    delta = np.full(n, np.nan)
    ok = np.zeros(n, bool)
    for i in range(n - HORIZON):
        if d.seg.iloc[i] == d.seg.iloc[i + HORIZON] and d.session.iloc[i] == d.session.iloc[i + HORIZON]:
            ok[i] = True
            delta[i] = d.close.iloc[i + HORIZON] - d.close.iloc[i]
    return delta, ok


def adverse(d, i, side):
    window = d.iloc[i + 1:i + HORIZON + 1]
    if side == 1:
        return float(d.close.iloc[i] - window.low.min())
    return float(window.high.max() - d.close.iloc[i])


def leakage(d, es, features):
    price = features.drop(columns=['log_rvol', 'log_rvol_lag1', 'log_volume5ratio'])
    cut = 500
    technical_prefix = base.ft.technical(d.iloc[:cut], es)
    pattern_prefix = base.ft.patterns(d.iloc[:cut])
    pd.testing.assert_frame_equal(technical_prefix, features.drop(columns=pattern_prefix.columns).iloc[:cut], check_exact=False, rtol=0, atol=1e-12)
    pd.testing.assert_frame_equal(pattern_prefix, features[pattern_prefix.columns].iloc[:cut], check_exact=False, rtol=0, atol=1e-12)
    mutated = es.copy()
    mutated.loc[mutated.index[-1], 'volume'] = float(mutated.volume.iloc[-1]) + 1000
    mutated_features = base.ft.technical(d, mutated)
    pd.testing.assert_frame_equal(mutated_features.iloc[:-1], features.drop(columns=pattern_prefix.columns).iloc[:-1], check_exact=False, rtol=0, atol=1e-12)
    model_bytes = (WF / 'models' / 'FIVE_MINS_price_900.json').read_bytes()
    log = pd.read_csv(WF / 'signals_derived.csv')
    selective = log[(log.frame == 'FIVE_MINS') & (log.variant == 'price') & (log.policy == 'selective')]
    state = json.loads((FWD / 'v2' / 'checkpoints' / '20261103T203227000000Z' / 'ARCHIVE_STATE.json').read_text())
    delays = []
    for signal in state['signals']:
        decision = pd.Timestamp(signal['decision_utc'])
        observed = pd.Timestamp(signal['observed_at_utc'])
        delays.append({
            'decision_Riyadh': signal['decision_Riyadh'],
            'result': signal['result'],
            'observation': signal['observation'],
            'seconds_from_bar_end_to_recorded_observation': (observed - decision).total_seconds(),
        })
    return {
        'prefix_features_unchanged_when_future_removed': True,
        'es_volume_revision_does_not_change_earlier_rows': True,
        'frozen_sha256': hashlib.sha256(model_bytes).hexdigest(),
        'frozen_sha_matches_recipe': hashlib.sha256(model_bytes).hexdigest() == FROZEN_SHA,
        'walkforward_selective_rows': int(len(selective)),
        'walkforward_scored': int(selective.scorable.sum()),
        'walkforward_hits': int((selective.loc[selective.scorable, 'signed_points'] > 0).sum()),
        'distinct_fold_models': int(selective.fold_start.nunique()),
        'availability_is_scheduled_bar_end_not_capture': True,
        'stable_archive_uses_caller_asof': 'research/frozen_forward_20261103/stable_archive.py rows() treats asof as knowledge time. archive_v2 defaults --asof to processing now. A late process can store a bar that was still forming at capture. The new watcher refuses that.',
        'scheduled_github_cron': '35 21 * * 1-5 UTC, once after the winter cash close, not on each five-minute close',
        'forward_observation_delays': delays,
        'sample_rows': len(d),
        'first_session': str(d.session.iloc[0]),
        'last_session': str(d.session.iloc[-1]),
        'locked_index': LOCKED_INDEX,
        'locked_boundary_Riyadh': str(d.available.iloc[LOCKED_INDEX].tz_convert('Asia/Riyadh')),
        'price_feature_count': int(price.shape[1]),
    }


def development(d, features, delta, ok):
    dev = np.arange(len(d)) < LOCKED_INDEX
    sessions = list(dict.fromkeys(d.session[dev]))
    cut = int(len(sessions) * 0.7)
    train_sessions = set(sessions[:cut])
    val_sessions = set(sessions[cut:])
    price = features.drop(columns=['log_rvol', 'log_rvol_lag1', 'log_volume5ratio'])
    common = np.isfinite(features.values).all(1)
    candidate = (features.filter(like='pattern_').values != 0).any(1)
    train = common & ok & dev & (delta != 0) & np.array([s in train_sessions for s in d.session])
    for i in np.flatnonzero(train):
        if d.session.iloc[i + HORIZON] not in train_sessions:
            train[i] = False
    model = make_pipeline(StandardScaler(), LogisticRegression(C=0.1, max_iter=2000, random_state=42))
    model.fit(price.values[train], delta[train] > 0)
    probability = np.full(len(d), np.nan)
    probability[common] = model.predict_proba(price.values[common])[:, 1]
    score = np.maximum(probability, 1 - probability)
    train_events = common & candidate & np.array([s in train_sessions for s in d.session]) & dev
    threshold = float(np.quantile(score[train_events], 0.9))
    side = np.where(probability >= 0.5, 1, -1)
    val = common & candidate & dev & np.array([s in val_sessions for s in d.session]) & (score >= threshold)
    last = None
    rows = []
    for i in np.flatnonzero(val):
        slot = int(d.slot.iloc[i])
        if last is not None and slot - last < 10:
            continue
        last = slot
        ret = float(price.return30.iloc[i])
        rows.append({
            'index': int(i),
            'decision_Riyadh': str(d.available.iloc[i].tz_convert('Asia/Riyadh')),
            'side': int(side[i]),
            'scorable': bool(ok[i]),
            'signed_points': float(side[i] * delta[i]) if ok[i] else None,
            'return30': ret,
            'continuation': continuation(int(side[i]), ret),
        })
    scored = [row for row in rows if row['scorable']]
    fails = [row for row in scored if row['signed_points'] <= 0]
    hits = [row for row in scored if row['signed_points'] > 0]
    return {
        'role': 'MOTIVATION_ONLY_NOT_THE_LOCKED_TEST',
        'train_sessions': sorted(train_sessions),
        'validation_sessions': sorted(val_sessions),
        'train_rows': int(train.sum()),
        'threshold_from_train_event_scores_labels_unused': threshold,
        'validation_selective_signals': len(rows),
        'validation_scored': len(scored),
        'validation_hits': len(hits),
        'validation_failures': len(fails),
        'failures_that_opposed_return30': sum(not row['continuation'] for row in fails),
        'hits_that_agreed_with_return30': sum(row['continuation'] for row in hits),
        'hypothesis_chosen_before_locked_scoring': 'H1_return30_continuation_veto',
        'rejected_prior_rule_not_repeated': 'EMA20 slope versus channel-20 midpoint plus three-bar retest',
        'rows': rows,
    }


def locked(d, features, delta, ok, dev_report):
    log = pd.read_csv(WF / 'signals_derived.csv')
    selective = log[(log.frame == 'FIVE_MINS') & (log.variant == 'price') & (log.policy == 'selective')].copy()
    lookup = {str(ts.tz_convert('Asia/Riyadh')): i for i, ts in enumerate(d.available)}
    price = features.drop(columns=['log_rvol', 'log_rvol_lag1', 'log_volume5ratio'])
    rows = []
    for record in selective.itertuples(index=False):
        i = lookup[record.decision_Riyadh]
        if i < LOCKED_INDEX:
            raise RuntimeError('selective signal fell inside the development window')
        ret = float(price.return30.iloc[i])
        keep = continuation(int(record.side), ret)
        signed = float(record.signed_points) if bool(record.scorable) else None
        rows.append({
            'index': int(i),
            'fold_start': int(record.fold_start),
            'decision_Riyadh': record.decision_Riyadh,
            'side': int(record.side),
            'scorable': bool(record.scorable),
            'signed_points': signed,
            'return30': ret,
            'continuation': keep,
            'adverse_points': adverse(d, i, int(record.side)) if bool(record.scorable) else None,
            'always_up_correct': bool(delta[i] > 0) if bool(record.scorable) else None,
        })
    before = [row for row in rows if row['scorable']]
    after = [row for row in before if row['continuation']]
    decision = adopt_filter(
        sum(row['signed_points'] > 0 for row in before),
        len(before),
        sum(row['signed_points'] > 0 for row in after),
        len(after),
    )
    def pack(group):
        if not group:
            return {'signals': 0, 'hits': 0, 'rate': None, 'wilson95': None, 'mean_signed_points': None, 'median_adverse_points': None}
        signed = np.array([row['signed_points'] for row in group])
        mae = np.array([row['adverse_points'] for row in group])
        hits = int((signed > 0).sum())
        return {
            'signals': len(group),
            'hits': hits,
            'rate': hits / len(group),
            'wilson95': wilson(hits, len(group)),
            'mean_signed_points': float(signed.mean()),
            'median_adverse_points': float(np.median(mae)),
            'worst_adverse_points': float(mae.max()),
        }
    always = [row for row in before if row['always_up_correct']]
    decision.update({
        'status': 'NOT_READY',
        'hypothesis': dev_report['hypothesis_chosen_before_locked_scoring'],
        'comparison': 'subset veto on the original selective log; cooldown of removed signals stays consumed; no regenerated signals and no new threshold',
        'before': pack(before),
        'after_continuation_veto': pack(after),
        'always_up_same_timestamps': {'hits': len(always), 'scored': len(before), 'rate': len(always) / len(before)},
        'costs': 'No bid/ask, commission, or option premium in this archive. adverse_points is the worst index move against the signal across the next six closed five-minute bars. It is not an option loss and not a recommended stop.',
        'multiplicity': 'Fourteen earlier policies already used this log. This is one additional pre-registered filter, not a fresh independent sample.',
        'forward_nov3_not_used': True,
    })
    return rows, decision


def forward_note(d):
    state = json.loads((FWD / 'v2' / 'checkpoints' / '20261103T203227000000Z' / 'ARCHIVE_STATE.json').read_text())
    lookup = {str(ts): i for i, ts in enumerate(d.available)}
    # The archived research frame ends November 2. Forward bars live only in the checkpoint.
    # Do not score the veto on them for adoption. Report the ledger as already observed.
    return {
        'used_for_adoption': False,
        'checkpoint': '20261103T203227000000Z',
        'signals': state['signals'],
        'correct': sum(row['result'] == 'CORRECT_ENDPOINT' for row in state['signals']),
        'incorrect': sum(row['result'] == 'INCORRECT_ENDPOINT' for row in state['signals']),
        'research_backfill': sum(row['observation'] == 'RESEARCH_BACKFILL' for row in state['signals']),
        'note': 'Two of three forward observations were recorded more than 180 seconds after bar end. A once-daily 21:35 UTC workflow cannot mark those bars at completion.',
        'archive_frame_has_index_for_forward_bars': any(str(ts) in lookup for ts in [row['decision_utc'] for row in state['signals']]),
    }


def main():
    protocol = {
        'frozen_model': 'research/multiframe_walkforward_20261103/models/FIVE_MINS_price_900.json',
        'frozen_sha256': FROZEN_SHA,
        'frozen_weights_and_threshold_immutable': True,
        'development_index_exclusive_end': LOCKED_INDEX,
        'locked_events': 'original FIVE_MINS price selective signals_derived rows, all expected at index >= 400',
        'hypothesis': 'Keep a selective signal only when sign(return30) equals the signal side. return30 is the causal 30-minute return already in the frozen feature list. This is not the rejected EMA20-versus-channel-midpoint retest.',
        'veto_consumes_original_cooldown': True,
        'no_regenerated_signals': True,
        'no_threshold_search': True,
        'adoption': 'shadow only if scored>=8, rate>=0.70, rate improves, removed correct signals < removed incorrect signals, and removed correct signals <= 2. A 70 percent claim also needs the Wilson 95 percent lower bound >= 0.70. trading_ready stays false.',
        'forward_ledger_excluded_from_adoption': '2026-11-03',
    }
    blob = json.dumps(protocol, indent=2).encode()
    (HERE / 'PROTOCOL.json').write_bytes(blob)
    (HERE / 'PROTOCOL.sha256').write_text(hashlib.sha256(blob).hexdigest() + '\n')
    d, es, features = load()
    delta, ok = outcomes(d)
    audit = leakage(d, es, features)
    dev = development(d, features, delta, ok)
    rows, decision = locked(d, features, delta, ok, dev)
    # The forward ledger cannot revise the decision object above.
    note = forward_note(d)
    if decision['frozen_weights_changed'] or decision['trading_ready'] or note['used_for_adoption']:
        raise RuntimeError('protocol breach')
    (HERE / 'LEAKAGE_AUDIT.json').write_text(json.dumps(audit, indent=2))
    (HERE / 'DEV_DIAGNOSIS.json').write_text(json.dumps(dev, indent=2))
    pd.DataFrame(rows).to_csv(HERE / 'locked_events.csv', index=False)
    (HERE / 'LOCKED_TEST.json').write_text(json.dumps(decision, indent=2))
    (HERE / 'FORWARD_LEDGER_NOTE.json').write_text(json.dumps(note, indent=2))
    result = {'status': 'NOT_READY', 'leakage_frozen_sha_ok': audit['frozen_sha_matches_recipe'], 'decision': decision, 'forward': {k: note[k] for k in ('correct', 'incorrect', 'research_backfill', 'used_for_adoption')}}
    (HERE / 'RESULT.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
