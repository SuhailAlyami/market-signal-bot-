"""Three fixed causal SPX lead hypotheses. Consumed-data development ONLY."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from hunter_research import ResearchConfig, score_signals
from replay_spx_price_watch import replay
from research_spx_premove import MODELS as V1_MODELS, features as v1_features
from research_spx_premove import preanchor_diagnostic, signal_schedule as v1_schedule

MODELS = ('slope_projection', 'acceleration_projection', 'prelevel_pressure')


def features(bars):
    f = v1_features(bars)
    dates = bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    for _, group in bars.groupby(dates, sort=False):
        for n in (3, 5, 10):
            weights = np.arange(n, dtype=float) - (n - 1) / 2
            denominator = float(weights @ weights)
            slope = group.Close.rolling(n).apply(lambda x: float(x @ weights / denominator), raw=True)
            f.loc[group.index, f'slope{n}'] = slope
        f.loc[group.index, 'prior_high20'] = group.High.shift(1).rolling(20).max()
        f.loc[group.index, 'prior_low20'] = group.Low.shift(1).rolling(20).min()
    return f


def directions(f, model):
    if model == 'slope_projection':
        up = ((3 * f.slope5 >= .5 * f.atr) & (f.close > f.ema15)
              & (f.body > 0) & (f.position >= .60))
        down = ((3 * f.slope5 <= -.5 * f.atr) & (f.close < f.ema15)
                & (f.body < 0) & (f.position <= .40))
    elif model == 'acceleration_projection':
        delta = f.slope3 - f.slope10
        up = ((f.slope3 > 0) & (delta >= f.atr / 6)
              & (3 * f.slope3 >= f.atr) & (f.body > 0))
        down = ((f.slope3 < 0) & (delta <= -f.atr / 6)
                & (3 * f.slope3 <= -f.atr) & (f.body < 0))
    elif model == 'prelevel_pressure':
        high_distance = f.prior_high20 - f.close
        low_distance = f.close - f.prior_low20
        up = ((high_distance > 0) & (high_distance <= .5 * f.atr)
              & (f.slope5 > 0) & (f.body > 0) & (f.position >= .65))
        down = ((low_distance > 0) & (low_distance <= .5 * f.atr)
                & (f.slope5 < 0) & (f.body < 0) & (f.position <= .35))
    else:
        raise ValueError('unknown_fixed_v2_model')
    out = pd.Series(0, index=f.index, dtype=int)
    out.loc[up & ~down & f.valid] = 1
    out.loc[down & ~up & f.valid] = -1
    return out


def schedule(f, model):
    signals, until = [], None
    for index, (timestamp, side) in enumerate(directions(f, model).items()):
        decision = timestamp + pd.Timedelta(minutes=1)
        if side and (until is None or decision >= until):
            signals.append(dict(index=index, direction=int(side), detected_at=decision.isoformat()))
            until = decision + pd.Timedelta(minutes=10)
    return signals


def audit_causality(bars, f):
    schedules = {name: schedule(f, name) for name in MODELS}
    prefix, poison = [], []
    for count in (31, 61, 91, 121, 151, 181, 211, 240):
        if count > len(bars):
            continue
        partial = features(bars.iloc[:count])
        prefix.append(dict(bars_available=count, matches={name:
            schedule(partial, name) == [s for s in schedules[name] if s['index'] < count]
            for name in MODELS}))
    for count in (61, 121, 181):
        if count >= len(bars):
            continue
        changed = bars.copy()
        changed.iloc[count:] += 1000
        future = features(changed)
        poison.append(dict(changed_from=count, matches={name:
            [s for s in schedule(future, name) if s['index'] < count] ==
            [s for s in schedules[name] if s['index'] < count] for name in MODELS}))
    return dict(prefix=prefix, future_poison=poison,
                passed=all(all(row['matches'].values()) for row in prefix + poison))


def development(source, output, protocol_commit):
    encoded = Path(source).read_bytes()
    payload = json.loads(encoded)
    with tempfile.TemporaryDirectory() as temp:
        baseline = replay(source, Path(temp) / 'baseline.json', protocol_commit)
    h = payload['history']
    cutoff = min(pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end']))
    bars = pd.DataFrame({key: h[key.lower()] for key in ('Open', 'High', 'Low', 'Close')},
                        index=pd.to_datetime(h['time'], utc=True))
    bars = bars.loc[bars.index + pd.Timedelta(minutes=1) <= cutoff]
    bars.attrs.update(symbol='SPX', security_type='IND')
    f, config = features(bars), ResearchConfig()
    eligible = [i for i in range(len(bars) - config.horizon) if f.valid.iloc[i]
                and bars.index[i + config.horizon] - bars.index[i] == pd.Timedelta(minutes=config.horizon)]
    if len(eligible) != baseline['metrics']['watch']['eligible_minutes']:
        raise ValueError('eligibility_changed')
    allowed, reports = set(eligible), {}
    for model in (*MODELS, *V1_MODELS):
        scheduled = schedule(f, model) if model in MODELS else v1_schedule(f, model)
        signals = [s for s in scheduled if s['index'] in allowed]
        report = dict(total_signals=len(scheduled), censored=len(scheduled) - len(signals),
                      strict={}, auxiliary={}, signal_matches={})
        for delay in (0, 1, 2):
            matched = [dict(s) for s in signals]
            report['strict'][str(delay)] = score_signals(
                baseline['events'], matched, bars, eligible, 'rth', config,
                bootstrap=False, availability_delay_minutes=delay)
            report['auxiliary'][str(delay)] = preanchor_diagnostic(baseline['events'], signals, bars, delay)
            report['signal_matches'][str(delay)] = matched
        reports[model] = report
    result = dict(mode='V2_CONSUMED_DEVELOPMENT_ONLY', protocol_commit=protocol_commit,
                  input_sha256=hashlib.sha256(encoded).hexdigest(), bars=len(bars),
                  events=baseline['events'], models=reports,
                  causality=audit_causality(bars, f), model_selected=None,
                  readiness='NOT_READY', accepted=False, independent_validation=False,
                  notifications_enabled=False, orders_enabled=False,
                  limitations=['Consumed partial Oct22 data; not independent validation.',
                               'New fixed hypotheses are development proposals only.',
                               'No parameter search, threshold change or matching change after execution.',
                               'Auxiliary pre-anchor results do not replace strict scoring.',
                               'No timing certainty, live latency measurement or option P&L.'])
    with Path(output).open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    result = development(args.input, args.output, args.protocol_commit)
    for model, row in result['models'].items():
        m = row['strict']['0']
        print(model, {k: m[k] for k in ('signals', 'early_matched_events', 'false_alarms', 'median_lead_minutes')},
              'early_by_delay', [row['strict'][str(d)]['early_matched_events'] for d in (0, 1, 2)],
              'aux_early', row['auxiliary']['0']['early_matches'])
