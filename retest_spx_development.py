"""Re-run consumed SPX data; audit causality and a conditional direction control.

No new model, threshold tuning, deployment, live feed or independent validation.
Direction randomization keeps observed signal times, so tests direction only;
its retrospective results cannot establish timing skill or qualify a detector.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from diagnose_spx_misses import diagnose
from hunter_research import ResearchConfig, score_signals
from research_spx_premove import MODELS, development, features, signal_schedule


def run(source, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    raw = Path(source).read_bytes()
    payload = json.loads(raw)
    h = payload['history']
    protocol = '355c2d8d728b119c4768c6767051132fe7afd8d6'
    replay = development(source, output / 'models.json', protocol)
    misses = diagnose(source, output / 'misses.json', protocol)
    cutoff = min(pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end']))
    bars = pd.DataFrame({k: h[k.lower()] for k in ('Open', 'High', 'Low', 'Close')},
                        index=pd.to_datetime(h['time'], utc=True))
    bars = bars.loc[bars.index + pd.Timedelta(minutes=1) <= cutoff]
    bars.attrs.update(symbol='SPX', security_type='IND')
    full = features(bars)
    schedules = {model: signal_schedule(full, model) for model in MODELS}
    prefix_rows = []
    for count in (31, 61, 91, 121, 151, 181, 211, 240):
        if count > len(bars):
            continue
        prefix = features(bars.iloc[:count])
        checked = {}
        for model in MODELS:
            expected = [s for s in schedules[model] if s['index'] < count]
            checked[model] = signal_schedule(prefix, model) == expected
        prefix_rows.append(dict(bars_available=count, matches_full_history_prefix=checked))
    future_rows = []
    for count in (61, 121, 181):
        if count >= len(bars):
            continue
        changed = bars.copy()
        changed.iloc[count:] = changed.iloc[count:] + 1000
        poisoned = features(changed)
        checked = {}
        for model in MODELS:
            expected = [s for s in schedules[model] if s['index'] < count]
            actual = [s for s in signal_schedule(poisoned, model) if s['index'] < count]
            checked[model] = actual == expected
        future_rows.append(dict(changed_from_index=count, earlier_signals_unchanged=checked))
    config = ResearchConfig()
    eligible = [i for i in range(len(bars) - config.horizon) if full.valid.iloc[i]
                and bars.index[i + config.horizon] - bars.index[i] == pd.Timedelta(minutes=config.horizon)]
    events = [{k: v for k, v in e.items() if k in (
        'event_id', 'anchor_index', 'target_index', 'direction', 'onset_time')}
        for e in misses['event_attribution']]
    controls = {}
    for model in MODELS:
        selected = replay['models'][model]['signals']
        rng = np.random.default_rng(20261023)
        counts = []
        for _ in range(100):
            randomized = [dict(s, direction=int(rng.choice((-1, 1)))) for s in selected]
            metric = score_signals(events, randomized, bars, eligible, 'rth', config, bootstrap=False)
            counts.append(metric['early_matched_events'])
        observed = replay['models'][model]['strict']['0']['early_matched_events']
        controls[model] = dict(observed_early=observed, random_direction_mean_early=float(np.mean(counts)),
                               random_direction_early_counts=counts,
                               empirical_upper_tail=(1 + sum(c >= observed for c in counts)) / 101,
                               conditional_on_observed_signal_times=True, diagnostic_only=True)
    all_pass = (all(all(r['matches_full_history_prefix'].values()) for r in prefix_rows)
                and all(all(r['earlier_signals_unchanged'].values()) for r in future_rows))
    result = dict(executed_at=datetime.now(timezone.utc).isoformat(),
                  input_sha256=hashlib.sha256(raw).hexdigest(), bars=len(bars), events=len(events),
                  source='IBKR_NATIVE_SPX_IND_CONSUMED_HISTORY', protocol_commit=protocol,
                  mode='REPEATED_CONSUMED_DEVELOPMENT_AUDIT',
                  prefix_audit=prefix_rows, future_poison_audit=future_rows,
                  causality_audit_passed=all_pass, direction_controls=controls,
                  randomization_seed=20261023, randomization_trials_per_model=100,
                  readiness='NOT_READY', accepted=False, model_selected=None,
                  independent_validation=False, notifications_enabled=False, orders_enabled=False,
                  limitations=['Same consumed partial session, not a new market sample.',
                               'No thresholds or matching rules changed to produce a pass.',
                               'Conditional random directions do not test candidate timing skill.',
                               'Empirical tails are descriptive; multiple models and consumed data invalidate confirmatory significance claims.',
                               'Prefix/poison checks cover the listed cutoffs, not every possible input.',
                               'No measured live latency or executable option performance.'])
    (output / 'audit.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(json.dumps({k: result[k] for k in ('bars', 'events', 'causality_audit_passed', 'readiness')}))
