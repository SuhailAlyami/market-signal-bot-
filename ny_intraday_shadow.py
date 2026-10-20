"""Prospective NY-session receipt journal for frozen rule/linear candidates.

No notifications or orders. Yahoo is unverified/delayed. First receipt, not a
historical candle close, is detection time. Boosted model stays offline-only.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from frozen_day_research import read_report
from hunter_crossmarket_research import signal as cross_rule
from hunter_linear_research import matrix_features, rule as model_rule
from hunter_research import validate_bars


def session_at(now):
    now = pd.Timestamp(now)
    if now.tz is None:
        raise ValueError('aware_clock_required')
    day = now.tz_convert('America/New_York').date()
    schedule = mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day)
    if schedule.empty:
        return None, 'NONTRADING_DAY'
    session = schedule.iloc[0]
    if now < session.market_open:
        return session, 'WAITING_FOR_NY_OPEN'
    if now >= session.market_close:
        return session, 'NY_CLOSED'
    return session, 'NY_OPEN'


def frozen_candidates(root):
    configs = {}
    fingerprints = {}
    for sym in ('ES', 'NQ'):
        configs[sym] = {}
        for kind, name, rule in (('crossmarket_v2', 'crossmarket', cross_rule),
                                 ('linear_v2', 'linear', model_rule)):
            report = read_report(root, kind, sym)
            selected = report['selected']
            configs[sym][name] = (selected.get('method', 'linear'), selected['params'], rule)
            path = root/'artifacts/detector_v2'/f'{kind}_{sym.lower()}_report.json.gz'
            fingerprints[f'{sym}_{name}'] = hashlib.sha256(path.read_bytes()).hexdigest()
    return configs, fingerprints


def observe(frames, configs, state, received_at, session):
    """Append first-seen completed bars and candidates; never infer outcomes."""
    received_at = pd.Timestamp(received_at)
    if received_at.tz is None:
        raise ValueError('aware_clock_required')
    state.setdefault('bars', {})
    state.setdefault('cooldown_until', {})
    records = []
    retained = {}
    for sym in ('ES', 'NQ'):
        data = validate_bars(frames[sym])
        data = data.loc[data.index+pd.Timedelta(minutes=1) <= received_at]
        if data.empty:
            raise ValueError('no_completed_bars')
        bars = state['bars'].setdefault(sym, {})
        for stamp, row in data.iterrows():
            key = stamp.isoformat()
            if key not in bars:
                # JSON rejects nonfinite prices; provider failures remain visible.
                bars[key] = {'values': row.tolist(), 'received_at': received_at.isoformat()}
        retained[sym] = pd.DataFrame([v['values'] for v in bars.values()],
                                    index=pd.to_datetime(list(bars), utc=True),
                                    columns=['Open','High','Low','Close','Volume']).sort_index()
    state.setdefault('evaluated', {})
    for sym, other in (('ES', 'NQ'), ('NQ', 'ES')):
        features = matrix_features(retained[sym], retained[other])
        for stamp, row in features.iterrows():
            if not session.market_open <= stamp < session.market_close:
                continue
            key = f'{sym}:{stamp.isoformat()}'
            if key in state['evaluated']:
                continue
            # Missing counterpart can arrive later. Wait instead of sealing a
            # false negative, and use the later actual receipt for detection.
            if stamp not in retained[other].index:
                continue
            state['evaluated'][key] = received_at.isoformat()
            end = stamp + pd.Timedelta(minutes=1)
            age = (received_at-end).total_seconds()
            for name, (method, params, rule) in configs[sym].items():
                identity = f'{sym}:{name}'
                until = state['cooldown_until'].get(identity)
                if until and stamp < pd.Timestamp(until):
                    continue
                direction = int(rule(row, method, params))
                if not direction:
                    continue
                state['cooldown_until'][identity] = (stamp+pd.Timedelta(minutes=10)).isoformat()
                records.append({'symbol': sym, 'candidate': name, 'direction': direction,
                                'bar_start': stamp.isoformat(), 'bar_close': end.isoformat(),
                                'detected_at': received_at.isoformat(), 'arrival_delay_seconds': age,
                                'timing_status': 'LATE' if age > 60 else 'WITHIN_ONE_MINUTE_UNVERIFIED_SOURCE',
                                'feed_realtime_verified': False, 'research_only': True,
                                'notifications_enabled': False, 'outcome': 'NOT_EVALUATED'})
    return records


def run(output, now=None, fetch=None, clock=None, root=None):
    root = Path(root or Path(__file__).parent)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = pd.Timestamp(now if now is not None else clock())
    session, status = session_at(now)
    report = {'status': status, 'checked_at': now.isoformat(), 'notifications_enabled': False,
              'readiness': 'NOT_READY', 'source': 'Yahoo ES=F / NQ=F, unverified latency',
              'code_revision': os.getenv('GITHUB_SHA'), 'new_candidates': [],
              'intraday_models': ['frozen_crossmarket', 'frozen_linear'],
              'offline_only_models': ['boosted'], 'polling': 'GitHub best effort, nominal 5 minutes'}
    if session is not None:
        report.update(market_open=session.market_open.isoformat(), market_close=session.market_close.isoformat())
    if status == 'NY_OPEN':
        configs, fingerprints = frozen_candidates(root)
        day = str(session.market_open.date())
        state_path = output/f'ny-{day}.json'
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if state and state['candidate_sha256'] != fingerprints:
            raise ValueError('frozen_candidates_changed_during_session')
        report['state_continuity'] = 'RESTORED' if state else 'NEW_OR_CACHE_MISSING'
        state['candidate_sha256'] = fingerprints
        report['candidate_sha256'] = fingerprints
        if fetch is None:
            import yfinance as yf
            fetch = lambda sym: yf.Ticker(sym+'=F').history(period='5d', interval='1m', auto_adjust=False, raise_errors=True)
        frames = {}
        try:
            for sym in ('ES', 'NQ'):
                frames[sym] = validate_bars(fetch(sym))
                if frames[sym].empty or not np.isfinite(frames[sym]).all().all():
                    raise ValueError('empty_or_nonfinite_provider_data')
        except Exception as exc:
            report.update(status='DATA_UNAVAILABLE', error_type=type(exc).__name__)
        else:
            received = pd.Timestamp(clock())
            records = observe(frames, configs, state, received, session)
            report.update(observed_at=received.isoformat(), new_candidates=records,
                          latest_bar_close={s:(f.index[f.index+pd.Timedelta(minutes=1)<=received].max()+pd.Timedelta(minutes=1)).isoformat() for s,f in frames.items()})
            state.setdefault('candidates', []).extend(records)
            temporary = state_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(state, allow_nan=False)+'\n')
            temporary.replace(state_path)
            with (output/f'ny-candidates-{day}.jsonl').open('a') as stream:
                for record in records:
                    stream.write(json.dumps(record, allow_nan=False)+'\n')
    (output/'ny-heartbeat.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as stream:
            stream.write('## New York intraday research — alerts OFF\n\n```json\n'+json.dumps(report, indent=2)+'\n```\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='.hunter-state/ny')
    result = run(parser.parse_args().output)
    print(json.dumps(result, allow_nan=False))
    raise SystemExit(1 if result['status']=='DATA_UNAVAILABLE' else 0)
