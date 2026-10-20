"""Bounded development search; freeze a candidate before opening replication data.

This tool never deploys thresholds or enables notifications. Related contracts
on the same market dates are correlated replication, not independent holdout.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path

from premium_radar import features, history_frame
from research_premium_radar import evaluate


def candidate_rule(config):
    def rule(f):
        distance = (f['prior_high'] - f['price']) / f['range']
        return (-2 <= distance <= config['distance']
                and f['rvol'] >= config['rvol']
                and f['return_1m'] >= config['return_1m'] and f['return_3m'] > 0)
    return rule


def load_sources(paths):
    sources = []
    for path in paths:
        blob = Path(path).read_bytes()
        data = history_frame(json.loads(blob))
        sources.append((hashlib.sha256(blob).hexdigest(), data,
                        [features(data, i) for i in range(len(data))]))
    if len({sha for sha, _, _ in sources}) != len(sources):
        raise ValueError('duplicate_source')
    return sources


def score(sources, config):
    rows = [evaluate(data, prepared=prepared, delay_seconds=60,
                     candidate=candidate_rule(config)) for _, data, prepared in sources]
    methods = {}
    for name in ('candidate', 'baseline_breakout', 'baseline_momentum'):
        methods[name] = {key: sum(row['methods'][name][key] for row in rows)
                         for key in ('signals', 'detected_events', 'early_events', 'false_alarms')}
    # Event counts across correlated contracts are never independent samples.
    return {'contract_events': sum(row['independent_events'] for row in rows), 'methods': methods}


def freeze(paths):
    sources = load_sources(paths)
    trials = []
    for rvol, ret, distance in itertools.product((1., 1.5, 2.), (.005, .015, .03), (.5, 1.5)):
        config = {'rvol': rvol, 'return_1m': ret, 'distance': distance}
        result = score(sources, config)
        m = result['methods']['candidate']
        utility = 2*m['early_events'] + m['detected_events'] - m['early_events'] - m['false_alarms']
        trials.append({'config': config, 'utility': utility, 'metrics': result})
    # Minimum signal support discourages choosing an isolated lucky hit.
    eligible = [trial for trial in trials if trial['metrics']['methods']['candidate']['signals'] >= 3]
    best = max(eligible, key=lambda trial: trial['utility']) if eligible else None
    return {'decision': 'NOT_READY', 'phase': 'DEVELOPMENT_FROZEN',
            'frozen_at': datetime.now(timezone.utc).isoformat(),
            'development_sha256': [sha for sha, _, _ in sources],
            'trial_count': len(trials), 'availability_delay_seconds': 60,
            'selected': best, 'trials': trials, 'notifications_enabled': False,
            'reason': 'exploratory_fit_requires_separate_replication_and_independent_sessions'}


def replicate(frozen, paths):
    if frozen.get('phase') != 'DEVELOPMENT_FROZEN' or not frozen.get('selected'):
        raise ValueError('frozen_candidate_required')
    sources = load_sources(paths)
    if set(frozen['development_sha256']) & {sha for sha, _, _ in sources}:
        raise ValueError('development_data_cannot_be_replication')
    config = frozen['selected']['config']
    result = score(sources, config)
    return {'decision': 'NOT_READY', 'phase': 'CORRELATED_CONTRACT_REPLICATION',
            'frozen_at': frozen['frozen_at'], 'config': config,
            'replication_sha256': [sha for sha, _, _ in sources], 'result': result,
            'notifications_enabled': False,
            'reason': 'same_market_dates_are_not_independent_sessions',
            'limitations': ['60-second arrival delay is assumed, not measured.',
                            'Trade highs do not establish executable option returns.',
                            'No automatic promotion: require chronological independent-session validation.',
                            'A matching event is not proof of a forecast before onset.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', nargs='+', required=True)
    parser.add_argument('--frozen', help='Existing frozen development JSON for replication')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = replicate(json.loads(Path(args.frozen).read_text()), args.inputs) if args.frozen else freeze(args.inputs)
    Path(args.output).write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'trials'}, indent=2))
