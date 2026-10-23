"""Compare frozen v1 vs corrective lifecycle on consumed data; never qualify."""
import argparse
import json
from pathlib import Path
import pandas as pd

from evaluate_spx_extension import load_history
from hunter_research import ResearchConfig, movement_events, score_signals
from research_spx_inside_range import _eligible, _wick_onset
from spx_inside_range import features, lifecycle
from spx_inside_range_safe import VERSION, lifecycle_safe


def compare(source, protocol):
    bars, _, digest, _ = load_history(source)
    groups = {day: group.copy() for day,group in bars.groupby(
        bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d'), sort=True)}
    boundary = pd.Timestamp('2026-10-22T17:30Z')
    day22 = groups['2026-10-22']
    segments = [('oct22_consumed_head', day22.loc[day22.index < boundary].copy(), None),
                ('oct22_consumed_tail', day22, boundary),
                ('oct21_backward_transfer', groups['2026-10-21'], None),
                ('oct20_partial_inventory', groups['2026-10-20'], None)]
    reports = []
    for name, segment, start in segments:
        segment.attrs.update(symbol='SPX', security_type='IND')
        frame = features(segment)
        eligible = _eligible(segment, frame, start)
        events = _wick_onset(segment, movement_events(segment, frame, eligible, ResearchConfig()))
        variants = {}
        for version, function in [('frozen_v1', lifecycle), ('corrective_v2', lifecycle_safe)]:
            rows = function(frame)
            if start is not None:
                rows = [row for row in rows if segment.index[row['index']] >= start]
            states = {}
            for state in ('READINESS','CONFIRMATION'):
                signals = [dict(index=row['index'], direction=row['direction'],detected_at=row['detected_at'])
                           for row in rows if row['state']==state and row['index'] in eligible]
                states[state] = {str(delay): score_signals(events, [dict(x) for x in signals],
                    segment, eligible, 'rth', ResearchConfig(), bootstrap=False,
                    availability_delay_minutes=delay) for delay in (0,1,2)}
            variants[version] = dict(transitions=rows, counts={state:sum(row['state']==state for row in rows)
                for state in ('READINESS','CONFIRMATION','CANCEL','EXIT')}, metrics=states)
        audit = []
        full = lifecycle_safe(frame)
        for count in (31,120,240):
            if count >= len(segment):
                continue
            prefix = segment.iloc[:count].copy()
            prefix.attrs.update(symbol='SPX',security_type='IND')
            poisoned = segment.copy(); poisoned.iloc[count:] += 1000
            expected = [row for row in full if row['index']<count]
            audit.append(dict(cutoff=count,
                prefix=lifecycle_safe(features(prefix))==expected,
                future_poison=[row for row in lifecycle_safe(features(poisoned)) if row['index']<count]==expected))
        reports.append(dict(name=name, events=len(events), variants=variants, causality=audit))
    if [row['events'] for row in reports] != [16,12,22,12]:
        raise ValueError('event_universe_drift')
    if not all(a['prefix'] and a['future_poison'] for row in reports for a in row['causality']):
        raise ValueError('causality_audit_failed')
    return dict(mode='CONSUMED_LIFECYCLE_CORRECTION', protocol_commit=protocol,
                input_sha256=digest, rule_version=VERSION, segments=reports,
                readiness='NOT_READY', accepted=False, independent_validation=False,
                notifications_enabled=False, orders_enabled=False,
                limitations=['Consumed historical sessions; no model selection or new thresholds.',
                             'No measured live arrival latency, option P&L, or delivery claims.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--protocol-commit',required=True)
    args = parser.parse_args()
    result = compare(args.input,args.protocol_commit)
    path = Path(args.output); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2,allow_nan=False)
        stream.write('\n')
    for row in result['segments']:
        print(row['name'], 'events',row['events'])
        for version,data in row['variants'].items():
            print(version, data['counts'], {state:{k:data['metrics'][state]['0'][k]
                for k in ('signals','early_matched_events','false_alarms','median_lead_minutes')}
                for state in ('READINESS','CONFIRMATION')})
    print('NOT_READY; all causality audits passed')
