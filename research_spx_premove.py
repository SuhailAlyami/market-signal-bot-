"""Frozen price-only SPX pre-movement hypotheses; development diagnostics only.

Never sends alerts or modifies a production detector. This command consumes the
already-used Oct22 fixture, not a training/validation/holdout acquisition.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from hunter_research import ResearchConfig, score_signals
from replay_spx_price_watch import replay
from spx_price_watch import observe

MODELS = ('compression_0.35', 'compression_0.50', 'compression_0.65',
          'pullback_release', 'sweep_reclaim', 'original_candidate', 'no_signal')


def features(bars):
    """Session-local causal features. OHLC only; no synthetic volume."""
    local = bars.copy()
    labels = local.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    blocks = []
    for _, group in local.groupby(labels, sort=False):
        f = pd.DataFrame(index=group.index)
        previous = group.Close.shift(1)
        tr = pd.concat([group.High-group.Low, (group.High-previous).abs(),
                        (group.Low-previous).abs()], axis=1).max(axis=1)
        f['atr'] = tr.shift(1).rolling(20).mean()
        span20 = group.High.shift(1).rolling(20).max()-group.Low.shift(1).rolling(20).min()
        span5 = group.High.shift(1).rolling(5).max()-group.Low.shift(1).rolling(5).min()
        f['compression'] = span5/span20.where(span20 > 0)
        f['position'] = (group.Close-group.Low)/(group.High-group.Low).replace(0, np.nan)
        f['body'] = group.Close-group.Open
        f['move3'] = group.Close-group.Close.shift(3)
        f['move15'] = group.Close-group.Close.shift(15)
        f['ema5'] = group.Close.ewm(span=5, adjust=False).mean()
        f['ema15'] = group.Close.ewm(span=15, adjust=False).mean()
        f['previous_close'] = previous
        f['previous_ema5'] = f.ema5.shift(1)
        f['close'] = group.Close
        # Reuse exact original validation and sweep semantics for every model.
        f['valid'] = [observe(group, i).get('prior_atr', 0) > 0 for i in range(len(group))]
        original = [observe(group, i).get('candidate') for i in range(len(group))]
        f['original_direction'] = [x['direction'] if x else 0 for x in original]
        f['sweep_direction'] = [x['direction'] if x and x['kind']=='SWEEP_RECLAIM' else 0 for x in original]
        blocks.append(f)
    return pd.concat(blocks) if blocks else pd.DataFrame(index=bars.index)


def directions(f, model):
    result = pd.Series(0, index=f.index, dtype=int)
    if model.startswith('compression_'):
        q = float(model.split('_')[1])
        up = (f.compression <= q) & (f.body > 0) & (f.move3 > 0) & (f.position >= .65)
        down = (f.compression <= q) & (f.body < 0) & (f.move3 < 0) & (f.position <= .35)
        result.loc[up] = 1
        result.loc[down] = -1
    elif model == 'pullback_release':
        up = ((f.ema5 > f.ema15) & (f.move15 > 0) &
              (f.previous_close <= f.previous_ema5) & (f.close > f.ema5) & (f.body > 0))
        down = ((f.ema5 < f.ema15) & (f.move15 < 0) &
                (f.previous_close >= f.previous_ema5) & (f.close < f.ema5) & (f.body < 0))
        result.loc[up] = 1
        result.loc[down] = -1
    elif model == 'sweep_reclaim':
        result = f.sweep_direction.astype(int).copy()
    elif model == 'original_candidate':
        result = f.original_direction.astype(int).copy()
    elif model != 'no_signal':
        raise ValueError('unknown_frozen_model')
    return result.where(f.valid, 0)


def signal_schedule(f, model):
    signals, until = [], None
    for i, (time, side) in enumerate(directions(f, model).items()):
        decision = time+pd.Timedelta(minutes=1)
        if side and (until is None or decision >= until):
            signals.append(dict(index=i, direction=int(side), detected_at=decision.isoformat()))
            until = decision+pd.Timedelta(minutes=10)
    return signals


def preanchor_diagnostic(events, signals, bars, delay=0):
    """Separate auxiliary metric; never substitutes for strict quality gates."""
    matched, leads = set(), []
    for signal in signals:
        delivered = pd.Timestamp(signal['detected_at'])+pd.Timedelta(minutes=delay)
        for e in events:
            target = bars.index[e['target_index']]
            onset = pd.Timestamp(e['onset_time'])
            if (e['event_id'] not in matched and e['direction']==signal['direction']
                    and bars.index[e['anchor_index']]-pd.Timedelta(minutes=3)
                    <= bars.index[signal['index']] < target
                    and delivered < onset and target >= delivered
                    and target <= delivered+pd.Timedelta(minutes=10)):
                matched.add(e['event_id'])
                leads.append((onset-delivered).total_seconds()/60)
                break
    return dict(early_matches=len(matched), signals=len(signals), events=len(events),
                early_precision=len(matched)/len(signals) if signals else None,
                early_recall=len(matched)/len(events) if events else None,
                median_lead_minutes=float(np.median(leads)) if leads else None,
                diagnostic_only=True)


def development(path, output, protocol_commit):
    raw = Path(path).read_bytes()
    payload = json.loads(raw)
    h = payload['history']
    with tempfile.TemporaryDirectory() as directory:
        baseline = replay(path, Path(directory)/'baseline.json', protocol_commit)
    cutoff = min(pd.Timestamp(payload['received_at']), pd.Timestamp(h['chart_end']))
    bars = pd.DataFrame({k: h[k.lower()] for k in ('Open','High','Low','Close')},
                        index=pd.to_datetime(h['time'], utc=True))
    bars = bars.loc[bars.index+pd.Timedelta(minutes=1) <= cutoff]
    bars.attrs.update(symbol='SPX', security_type='IND')
    f = features(bars)
    config = ResearchConfig()
    eligible = [i for i in range(len(bars)-config.horizon) if f.valid.iloc[i]
                and bars.index[i+config.horizon]-bars.index[i]==pd.Timedelta(minutes=config.horizon)]
    if len(eligible) != baseline['metrics']['watch']['eligible_minutes']:
        raise ValueError('development_fixture_eligibility_changed')
    metrics = {}
    for model in MODELS:
        all_signals = signal_schedule(f, model)
        signals = [s for s in all_signals if s['index'] in eligible]
        metrics[model] = dict(total_signals=len(all_signals), censored=len(all_signals)-len(signals),
                              strict={}, auxiliary={}, signals=signals)
        for delay in (0,1,2):
            metrics[model]['strict'][str(delay)] = score_signals(
                baseline['events'], [dict(s) for s in signals], bars, eligible, 'rth', config,
                bootstrap=False, availability_delay_minutes=delay)
            metrics[model]['auxiliary'][str(delay)] = preanchor_diagnostic(
                baseline['events'], signals, bars, delay)
    result = dict(protocol_commit=protocol_commit, input_sha256=hashlib.sha256(raw).hexdigest(),
                  mode='CONSUMED_OCT22_DEVELOPMENT_SMOKE_ONLY', bars=len(bars),
                  events=len(baseline['events']), models=metrics,
                  independent_acquisition='ONE_MONTH/ONE_MIN rejected twice by IBKR connector; no raw provider error persisted',
                  quality_splits='NOT_RUN_INSUFFICIENT_INDEPENDENT_COVERAGE',
                  model_selected=None, holdout_opened=False, accepted=False,
                  readiness='NOT_READY', notifications_enabled=False, orders_enabled=False,
                  full_sessions=0, partial_sessions=1,
                  limitations=['No train/validation/holdout claims from consumed data.',
                               'Fixed ten-minute candidate cooldown; does not use outcome to schedule.',
                               'Strict anchor metric and three-minute pre-anchor diagnostic reported separately.',
                               'No native intraminute ordering or measured live arrival latency.',
                               'No threshold was changed after the frozen protocol.'])
    Path(output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--protocol-commit', required=True)
    args = parser.parse_args()
    result = development(args.input, args.output, args.protocol_commit)
    for name, data in result['models'].items():
        m = data['strict']['0']
        print(name, {k:m[k] for k in ('signals','matched_events','early_matched_events','false_alarms','median_lead_minutes')},
              'aux_early', data['auxiliary']['0']['early_matches'])
