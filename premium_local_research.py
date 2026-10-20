"""Local premium breakout hypotheses; development selection, frozen replication.

Related strikes share exposure and market sessions. These experiments cannot
establish independent-session SPX 0DTE prediction or executable option returns.
"""
from datetime import timedelta
import hashlib
import itertools
import json
from pathlib import Path

import pandas as pd

from premium_radar import features, history_frame, classify_features

GRID = tuple({'lookback': lookback, 'rvol': rvol, 'min_return': ret}
             for lookback, rvol, ret in itertools.product((3, 5), (1.5, 2.5), (.015, .03)))


def prepare(data):
    rows = []
    for i in range(len(data)):
        f = features(data, i)
        if f is not None:
            f = dict(f)
            for size in (3, 5):
                f[f'local_high_{size}'] = float(data.High.iloc[i-size:i].max())
            f['body_fraction'] = float((data.Close.iloc[i]-data.Low.iloc[i]) /
                                       max(data.High.iloc[i]-data.Low.iloc[i], 1e-9))
        rows.append(f)
    return rows


def local_rule(f, config):
    return (f['price'] > f['local_high_'+str(config['lookback'])]
            and f['rvol'] >= config['rvol'] and f['return_1m'] >= config['min_return']
            and f['return_3m'] > 0 and f['body_fraction'] >= .6)


def evaluate(data, prepared, config, delay=60):
    names = ('local', 'current_watch', 'current_acceleration', 'baseline_breakout', 'baseline_momentum')
    scheduled, cooldown = {name: [] for name in names}, {}
    valid = [f is not None for f in prepared]
    observable = {}
    # Causal signal generation/cooldown precedes any future availability/label.
    for i, f in enumerate(prepared):
        if f is None:
            continue
        signal = classify_features(f, data.index[i].to_pydatetime()+timedelta(minutes=1))
        rules = {'local': local_rule(f, config),
                 'current_watch': signal is not None and signal['state'] == 'WATCH',
                 'current_acceleration': signal is not None and signal['state'] == 'ACCELERATION',
                 'baseline_breakout': f['price'] > f['prior_high'],
                 'baseline_momentum': f['return_1m'] >= .03}
        decision = data.index[i]+pd.Timedelta(minutes=1, seconds=delay)
        for name, active in rules.items():
            if active and (name not in cooldown or decision >= cooldown[name]):
                cooldown[name] = decision+pd.Timedelta(minutes=5)
                scheduled[name].append({'index': i, 'decision': decision})
    for i in range(20, len(data)-5):
        observable[i] = (all(valid[i:i+6]) and
                         (data.index[i:i+6].to_series().diff().iloc[1:] == pd.Timedelta(minutes=1)).all())
    events, next_anchor = [], -1
    for i in range(20, len(data)-5):
        if i < next_anchor or not observable[i]:
            continue
        anchor = float(data.Close.iloc[i])
        hits = [j for j in range(i+1,i+6) if data.High.iloc[j] >= 1.25*anchor]
        if not hits:
            continue
        hit = hits[0]
        onset = next(j for j in range(i+1,hit+1) if data.High.iloc[j] >= 1.05*anchor)
        events.append({'anchor': data.index[i]+pd.Timedelta(minutes=1),
                       'onset': data.index[onset], 'target': data.index[hit]})
        # Identical +25%/5m event definition to the retained premium pilot.
        next_anchor = hit+1
    results = {}
    for name, signals in scheduled.items():
        scored = [s for s in signals if observable.get(s['index'], False)]
        used, matches = set(), []
        for s in scored:
            for k, event in enumerate(events):
                if k not in used and event['anchor'] <= s['decision'] <= event['target']:
                    used.add(k)
                    lead = (event['onset']-s['decision']).total_seconds()
                    matches.append({'decision':s['decision'].isoformat(), 'onset':event['onset'].isoformat(),
                                    'target':event['target'].isoformat(), 'lead_seconds':lead})
                    break
        early = sum(m['lead_seconds']>0 for m in matches)
        timely = sum(m['lead_seconds']>=-60 for m in matches)
        n, e, h = len(scored), len(events), len(matches)
        p, r = timely/n if n else 0., timely/e if e else 0.
        results[name] = {'signals':n,'censored_signals':len(signals)-n,'events':e,'detected':h,
                         'before_onset':early,'within_first_minute_or_before':timely,
                         'late_detections':h-timely, 'false_alarms':n-h,'missed_events':e-h,
                         'precision':h/n if n else None,'recall':h/e if e else None,
                         'timely_precision':p if n else None,'timely_recall':r if e else None,
                         'timely_f1':2*p*r/(p+r) if p+r else 0.,
                         'median_lead_seconds':float(pd.Series([m['lead_seconds'] for m in matches]).median()) if matches else None,
                         'matches':matches}
    return results


def load(paths):
    result = []
    for path in paths:
        blob = Path(path).read_bytes()
        data = history_frame(json.loads(blob))
        result.append((hashlib.sha256(blob).hexdigest(), data, prepare(data)))
    return result


def aggregate(sources, config, delay=60):
    rows = [evaluate(data, prepared, config, delay) for _, data, prepared in sources]
    methods = {}
    for name in rows[0]:
        keys = ('signals','censored_signals','events','detected','before_onset','within_first_minute_or_before',
                'late_detections','false_alarms','missed_events')
        m = {key:sum(row[name][key] for row in rows) for key in keys}
        p = m['within_first_minute_or_before']/m['signals'] if m['signals'] else 0.
        r = m['within_first_minute_or_before']/m['events'] if m['events'] else 0.
        m.update(timely_precision=p if m['signals'] else None, timely_recall=r if m['events'] else None,
                 timely_f1=2*p*r/(p+r) if p+r else 0.)
        methods[name] = m
    return {'methods':methods, 'contract_reports':rows, 'delay_seconds':delay,
            'source_sha256':[sha for sha,_,_ in sources]}


def develop(train_paths, validation_paths):
    train, validation = load(train_paths), load(validation_paths)
    if {x[0] for x in train} & {x[0] for x in validation}:
        raise ValueError('overlapping_sources')
    trials = [{'config':c, 'train':aggregate(train,c)} for c in GRID]
    eligible = [x for x in trials if x['train']['methods']['local']['signals'] >= 3]
    ranked = sorted(eligible, key=lambda x:(-x['train']['methods']['local']['timely_f1'],
                                            x['train']['methods']['local']['false_alarms'],json.dumps(x['config'],sort_keys=True)))
    finalists = [{**x,'validation':aggregate(validation,x['config'])} for x in ranked[:2]]
    selected = sorted(finalists,key=lambda x:(-x['validation']['methods']['local']['timely_f1'],
                                             x['validation']['methods']['local']['false_alarms'],json.dumps(x['config'],sort_keys=True)))[0] if finalists else None
    return {'status':'NOT_READY','grid_size':len(GRID),'trials':trials,'finalists':finalists,'selected':selected,
            'train_sha256':[x[0] for x in train],'validation_sha256':[x[0] for x in validation],
            'timing_protocol':'Decision = completed minute end plus 60 seconds assumed availability. Onset/target = first threshold-touch minute START. Timely = decision no later than onset+60 seconds.',
            'data_scope':'Previously inspected related 7690 development / 7695 validation contracts on shared market dates; not independent sessions or historical 0DTE.',
            'notifications_enabled':False}
