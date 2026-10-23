"""Attribute SPX development misses without changing detector or scoring rules.

Future event labels are used ONLY for retrospective attribution. The raw-candidate
counterfactual is deliberately diagnostic: it removes lifecycle suppression, not
the detector's price conditions, and is not an alternative deployable strategy.
"""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import tempfile

import pandas as pd

from hunter_research import ResearchConfig, score_signals
from replay_spx_price_watch import replay
from spx_price_runtime import SPXPriceRuntime
from spx_price_watch import observe


def diagnose(path, output, protocol_commit):
    payload = json.loads(Path(path).read_bytes())
    h = payload['history']
    cutoff = min(pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end']))
    bars = pd.DataFrame({k: h[k.lower()] for k in ('Open', 'High', 'Low', 'Close')},
                        index=pd.to_datetime(h['time'], utc=True))
    bars = bars.loc[bars.index + pd.Timedelta(minutes=1) <= cutoff]
    bars.attrs.update(symbol='SPX', security_type='IND')
    config = ResearchConfig()
    with tempfile.TemporaryDirectory() as directory:
        base = replay(path, Path(directory)/'baseline.json', protocol_commit)
        runtime = SPXPriceRuntime(Path(directory)/'state.json', Path(directory)/'journal.jsonl')
        trace, raw, watch, triggers = [], [], [], []
        for i in range(len(bars)):
            obs = observe(bars, i)
            end = bars.index[i] + pd.Timedelta(minutes=1)
            if i < 30 or not runtime.market_is_open(end.to_pydatetime()):
                continue
            before = deepcopy(runtime.state['symbols'].get('SPX', {}))
            found = obs['candidate']
            emitted = runtime._process_bar('SPX', bars, i, end.to_pydatetime())
            stages = [e['state'] for e in emitted]
            if found:
                signal = dict(index=i, direction=found['direction'],
                              detected_at=end.isoformat(), pattern=found['kind'])
                raw.append(signal)
            for e in emitted:
                signal = dict(index=i, direction=1 if e['direction']=='UP' else -1,
                              detected_at=end.isoformat(), pattern=e['pattern'])
                if e['state']=='SETUP':
                    watch.append(signal)
                elif e['state']=='TRIGGER':
                    triggers.append(signal)
            active = before.get('active')
            if not found:
                gate = 'no_price_candidate'
            elif 'SETUP' in stages:
                gate = 'new_setup'
            elif active:
                # Opposite candidates are preempted by SPXPriceRuntime, so this
                # is an already-active same-direction scenario (or its exit bar).
                gate = 'same_direction_active_or_exit_bar'
            elif before.get('cooldown_until') and end < pd.Timestamp(before['cooldown_until']):
                gate = 'cooldown'
            else:
                gate = 'other'
            trace.append(dict(index=i, decision_at=end.isoformat(), reason=obs['reason'],
                              previous_phase=active['phase'] if active else None,
                              previous_started_at=active['started_at'] if active else None,
                              candidate_direction=found['direction'] if found else 0,
                              candidate_pattern=found['kind'] if found else None,
                              gate=gate, emitted=[dict(state=e['state'], direction=e['direction'],
                                                     reason=e['reason']) for e in emitted]))

    # Recreate eligibility exactly as the baseline on this validated contiguous
    # fixture; unavailable future windows are censored, never counted as failures.
    eligible = [t['index'] for t in trace if t['index']+config.horizon < len(bars)
                and bars.index[t['index']+config.horizon]-bars.index[t['index']]
                == pd.Timedelta(minutes=config.horizon)]
    expected = base['metrics']['watch']['eligible_minutes']
    if len(eligible) != expected:
        raise ValueError('diagnostic_eligibility_differs_from_baseline')
    for stage, actual in [('watch', watch), ('confirmations', triggers)]:
        if actual != base[stage]:
            raise ValueError('runtime_trace_differs_from_baseline')
    scored = {}
    for stage, signals in [('raw_candidates_no_lifecycle', raw), ('watch', watch),
                           ('confirmation', triggers)]:
        scored[stage] = {}
        for delay in (0, 1, 2):
            selected = [dict(s) for s in signals if s['index'] in eligible]
            scored[stage][str(delay)] = score_signals(
                base['events'], selected, bars, eligible, 'rth', config,
                bootstrap=False, availability_delay_minutes=delay)

    event_rows = []
    for e in base['events']:
        onset = pd.Timestamp(e['onset_time'])
        # Preserve the strict anchor and target window. No retroactive warning
        # before the anchor is awarded a success, even if visually appealing.
        window = [s for s in raw if e['anchor_index'] <= s['index'] < e['target_index']
                  and s['direction']==e['direction']]
        early = [s for s in window if pd.Timestamp(s['detected_at']) < onset]
        early_watch = [s for s in watch if e['anchor_index'] <= s['index'] < e['target_index']
                       and s['direction']==e['direction'] and pd.Timestamp(s['detected_at']) < onset]
        if early_watch:
            cause = 'early_watch_present'
        elif early:
            cause = 'early_raw_candidate_suppressed_by_lifecycle'
        elif window:
            cause = 'first_price_candidate_at_or_after_onset'
        else:
            cause = 'no_matching_price_candidate_before_target'
        early_indices = {s['index'] for s in early}
        pre = [t for t in trace if e['anchor_index'] <= t['index'] < e['target_index']
               and pd.Timestamp(t['decision_at']) < onset]
        event_rows.append({**e, 'onset_time': onset.isoformat(),
                           'anchor_decision_at': (bars.index[e['anchor_index']]+pd.Timedelta(minutes=1)).isoformat(),
                           'minutes_from_anchor_decision_to_onset':
                           (onset-bars.index[e['anchor_index']]-pd.Timedelta(minutes=1)).total_seconds()/60,
                           'diagnostic_cause': cause,
                           'first_matching_candidate': window[0] if window else None,
                           'early_raw_candidates': early, 'early_watch': early_watch,
                           'early_suppression_gates': dict(Counter(t['gate'] for t in trace if t['index'] in early_indices)),
                           'pre_onset_observation_reasons': dict(Counter(t['reason'] for t in pre))})
    report = dict(mode='CONSUMED_DEVELOPMENT_MISS_ATTRIBUTION',
                  input_sha256=base['input_sha256'], protocol_commit=protocol_commit,
                  detector_version=base['rule_version'], bars=base['bars'],
                  first_eligible_decision=base['first_eligible_decision'],
                  excluded_opening_bars=30, events=len(event_rows),
                  attribution_counts=dict(Counter(e['diagnostic_cause'] for e in event_rows)),
                  events_without_strict_pre_onset_decision_window=sum(
                      e['minutes_from_anchor_decision_to_onset'] <= 0 for e in event_rows),
                  raw_candidate_count=len(raw), lifecycle_watch_count=len(watch),
                  candidate_gate_counts=dict(Counter(t['gate'] for t in trace if t['candidate_direction'])),
                  metrics_with_delivery_delay_minutes=scored, event_attribution=event_rows,
                  trace=trace, holdout=False, readiness='NOT_READY',
                  detector_changed=False, notifications_enabled=False,
                  limitations=['One consumed partial SPX session; no untouched validation.',
                               'Onset minute start is conservative; intraminute ordering is unknown.',
                               'Attribution presence is not one-to-one performance; metrics remain strict one-to-one.',
                               'Raw-candidate ablation is diagnostic, not a selected strategy.',
                               'Delay scenarios are deterministic sensitivities, not measured live latency.'])
    Path(output).write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    result = diagnose(args.input, args.output, args.protocol_commit)
    print(json.dumps({k: result[k] for k in ('events', 'attribution_counts',
                                           'candidate_gate_counts', 'readiness')}))
