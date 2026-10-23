"""Describe timing failure from saved TRAINING results; never retune or open holdout."""
import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path


def diagnose(report):
    training = report['train']
    events = training['events']
    no_slot = sum(datetime.fromisoformat(e['onset_time']) <=
                  datetime.fromisoformat(e['anchor_time']) + timedelta(minutes=1)
                  for e in events)
    models = {}
    for name, value in training['models'].items():
        matched = [s for s in value['signal_matches']['0'] if s.get('event_id') is not None]
        early = sum(s['lead_minutes'] > 0 for s in matched)
        on_time = sum(s['lead_minutes'] == 0 for s in matched)
        late = sum(s['lead_minutes'] < 0 for s in matched)
        metric = value['strict']['0']
        if len(matched) != metric['matched_events'] or early != metric['early_matched_events']:
            raise ValueError('saved_match_metric_inconsistency')
        if early + on_time + late != len(matched):
            raise ValueError('invalid_saved_lead')
        models[name] = dict(signals=metric['signals'], matched=len(matched),
                            early=early, at_onset=on_time, late=late,
                            unmatched=metric['signals'] - len(matched),
                            early_precision=metric['early_precision'],
                            median_lead_minutes=metric['median_lead_minutes'])
    return dict(mode='CONSUMED_TRAINING_DIAGNOSTIC_ONLY', days=training['days'],
                events=len(events),
                constrained_anchor_windows_without_strict_early_slot=no_slot,
                models=models, thresholds_changed=False, holdout_computed=False,
                readiness='NOT_READY', limitations=[
                    'An empty anchor-constrained window does not exclude earlier signals before that anchor.',
                    'Late matched signals describe timing; this alone does not prove a causal bug.',
                    'No candidate, gate, matching rule, validation result or alert setting is changed.',
                    'Training outcomes are consumed development evidence, not an independent test.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    encoded = args.study.read_bytes()
    result = diagnose(json.loads(encoded))
    result['study_sha256'] = hashlib.sha256(encoded).hexdigest()
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
