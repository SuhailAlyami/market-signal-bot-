"""Replay native SPX observations at their recorded availability, never final OHLC.

Offline diagnostic only. Parallel quote mode is evidence, not an exchange trade
timestamp or proof that an HMDS bar is a final, real-time revision.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median
from zoneinfo import ZoneInfo

import pandas as pd

from spx_price_watch import observe

UTC = timezone.utc
FIELDS = ('open', 'high', 'low', 'close')


def clock(value):
    stamp = datetime.fromisoformat(value)
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError('aware_receipt_required')
    return stamp.astimezone(UTC)


def checked_bar(row):
    stamp = int(row['time'])
    if str(stamp) != str(row['time']) or stamp <= 0 or stamp % 60:
        raise ValueError('unaligned_provider_bar')
    values = tuple(float(row[k]) for k in FIELDS)
    o, h, l, c = values
    if (not all(math.isfinite(v) and v > 0 for v in values)
            or h < max(values) or l > min(values)):
        raise ValueError('invalid_provider_prices')
    return stamp, values


class AsOfTrace:
    def __init__(self, events, opened, closed):
        self.opened, self.closed = opened, closed
        if opened.tzinfo is None or closed.tzinfo is None or opened >= closed:
            raise ValueError('aware_session_bounds_required')
        self.versions, self.first, self.issues = {}, {}, Counter()
        self.decisions = []
        self.mode_events = []
        identities, subscriptions, connections, modes = set(), {}, {}, {}
        previous = None
        for event in events:
            received = clock(event['received_at'])
            if previous is not None and received < previous:
                raise ValueError('receipt_clock_regression')
            previous = received
            connection = event.get('connection')
            if not isinstance(connection, str) or not connection:
                raise ValueError('connection_identity_required')
            kind = event['kind']
            if kind == 'start':
                if (event.get('symbol'), event.get('security_type'), event.get('exchange'),
                        event.get('currency')) != ('SPX', 'IND', 'CBOE', 'USD'):
                    raise ValueError('native_spx_identity_required')
                if clock(event['session_open']) != opened or clock(event['session_close']) != closed:
                    raise ValueError('session_identity_mismatch')
                identities.add(connection)
                connections[connection] = received
                self.mode_events.append((received, None))
                if event.get('resumed_with_corrupt_log'):
                    self.issues['recorder_reported_corrupt_log'] += 1
            elif kind == 'connect_attempt':
                if not identities:
                    raise ValueError('native_spx_start_required')
                identities.add(connection)
                connections[connection] = received
                self.mode_events.append((received, None))
            elif kind == 'subscriptions':
                if connection not in identities:
                    raise ValueError('unverified_connection')
                contract = event.get('contract_id')
                if type(contract) is not int or contract <= 0:
                    raise ValueError('contract_identity_required')
                if subscriptions and contract not in subscriptions.values():
                    raise ValueError('contract_identity_changed')
                subscriptions[connection] = contract
            elif kind == 'market_data_type':
                if connection not in subscriptions:
                    raise ValueError('subscription_identity_required')
                modes[connection] = event.get('market_data_type')
                self.mode_events.append((received, modes[connection]))
            elif kind in ('first_completed_observation', 'historical_update'):
                if connection not in subscriptions:
                    raise ValueError('subscription_identity_required')
                stamp, values = checked_bar(event['bar'])
                if not opened.timestamp() <= stamp < closed.timestamp():
                    self.issues['outside_session'] += 1
                    continue
                if received.timestamp() < stamp + 60:
                    if kind == 'first_completed_observation':
                        raise ValueError('completed_before_bar_end')
                    continue  # An unfinished update cannot drive a decision.
                if kind == 'first_completed_observation':
                    if stamp + 60 < connections[connection].timestamp():
                        raise ValueError('preconnection_bar_is_not_prospective')
                    if stamp in self.first:
                        raise ValueError('duplicate_first_availability')
                    if event.get('provider_bar_end') != stamp + 60:
                        raise ValueError('provider_bar_end_mismatch')
                    if event.get('completion_evidence') not in (
                            'provider_advanced_to_later_bar', 'live_update_received_after_bar_end'):
                        raise ValueError('completion_evidence_required')
                    self.first[stamp] = (received, values)
                    self.decisions.append(received)
                elif stamp not in self.first:
                    continue  # Await explicit completion evidence; never use backfill.
                mode = event.get('parallel_quote_mode')
                if mode != modes.get(connection):
                    raise ValueError('quote_mode_evidence_mismatch')
                self.versions.setdefault(stamp, []).append((received, values, mode))
            # historical_backfill and standalone quote timestamps are not availability.
        if not identities:
            raise ValueError('native_spx_start_required')
        self.contract_id = next(iter(subscriptions.values())) if subscriptions else None

    def snapshot(self, at):
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('aware_decision_required')
        selected = {}
        for stamp, versions in self.versions.items():
            available = [v for v in versions if v[0] <= at]
            if available:
                selected[stamp] = available[-1]
        stamps = sorted(selected)
        frame = pd.DataFrame([selected[s][1] for s in stamps],
                             columns=['Open', 'High', 'Low', 'Close'],
                             index=pd.to_datetime(stamps, unit='s', utc=True))
        frame.attrs.update(symbol='SPX', security_type='IND',
                           source='IBKR_PROSPECTIVE_ASOF_DIAGNOSTIC', live_feed_verified=False)
        status = 'warming_up_or_gap'
        current_modes = [mode for received, mode in self.mode_events if received <= at]
        if len(stamps) >= 31 and all(b-a == 60 for a, b in zip(stamps[-31:], stamps[-30:])):
            age = at.timestamp() - stamps[-1] - 60
            if age > 120:
                status = 'stale_bar'
            elif not current_modes or current_modes[-1] != 1 or any(selected[s][2] != 1 for s in stamps[-31:]):
                status = 'quote_mode_unverified'
            else:
                status = 'ok'
        return frame, status

    def decision(self, at):
        frame, status = self.snapshot(at)
        if not self.opened <= at < self.closed:
            status = 'cash_session_closed'
        result = observe(frame, len(frame)-1) if status == 'ok' else {'candidate': None, 'reason': status}
        return dict(detected_at=at.astimezone(UTC).isoformat(),
                    bar_end=(frame.index[-1]+pd.Timedelta(minutes=1)).isoformat() if len(frame) else None,
                    candidate=result['candidate'], reason=result['reason'],
                    readiness='NOT_READY', notify_eligible=False,
                    availability='recorded_local_receipt', live_feed_verified=False)


def diagnose(trace_path, capture_path, output):
    trace_bytes, capture_bytes = Path(trace_path).read_bytes(), Path(capture_path).read_bytes()
    events = [json.loads(line) for line in trace_bytes.decode('utf-8').splitlines()]
    starts = [e for e in events if e.get('kind') == 'start']
    if not starts:
        raise ValueError('native_spx_start_required')
    from spx_availability_recorder import session_bounds
    bounds = session_bounds(clock(starts[0]['session_open']).astimezone(
        ZoneInfo('America/New_York')).date().isoformat())
    if bounds is None:
        raise ValueError('no_cash_session')
    opened, closed = bounds
    trace = AsOfTrace(events, opened, closed)
    raw = json.loads(capture_bytes)
    expected_identity = dict(symbol='SPX', security_type='IND', exchange='CBOE',
                             currency='USD', contract_id=trace.contract_id)
    if trace.contract_id is None or raw.get('contract') != expected_identity:
        raise ValueError('capture_identity_mismatch')
    if clock(raw['received_at']) < closed:
        raise ValueError('capture_before_session_close')
    from collect_spx_sessions import validate_session
    final_coverage = validate_session(raw['rows'], opened, closed)
    final = dict(checked_bar(r) for r in raw['rows'] if opened.timestamp() <= int(r['time']) < closed.timestamp())
    expected = set(range(int(opened.timestamp()), int(closed.timestamp()), 60))
    matched = sorted(set(trace.first) & set(final))
    revised = [s for s in matched if trace.first[s][1] != final[s]]
    lags = sorted((v[0].timestamp()-s-60) for s, v in trace.first.items())
    decisions = [trace.decision(t) for t in sorted(set(trace.decisions)) if t < closed]
    counts = Counter(d['reason'] for d in decisions)
    report = dict(schema_version=1, trace_sha256=hashlib.sha256(trace_bytes).hexdigest(),
                  capture_sha256=hashlib.sha256(capture_bytes).hexdigest(),
                  source='NATIVE_SPX_PROSPECTIVE_AVAILABILITY_DIAGNOSTIC',
                  session_open=opened.isoformat(), session_close=closed.isoformat(),
                  expected_minutes=len(expected), prospective_minutes=len(trace.first),
                  missing_prospective_minutes=len(expected-set(trace.first)),
                  full_prospective_trace=(set(trace.first) == expected
                      and min(clock(e['received_at']) for e in starts) <= opened
                      and not trace.issues['recorder_reported_corrupt_log']
                      and all(trace.versions[s][0][2] == 1 for s in trace.first)),
                  final_capture_complete=final_coverage['complete'],
                  first_snapshot_differs_from_final=len(revised), compared_minutes=len(matched),
                  local_availability_lag_seconds=dict(min=lags[0] if lags else None,
                      median=median(lags) if lags else None,
                      max=lags[-1] if lags else None),
                  decision_reason_counts=dict(counts), decisions=decisions,
                  issues=dict(trace.issues), readiness='NOT_READY', holdout=False,
                  signal_quality_evaluated=False, notifications_enabled=False, orders_enabled=False,
                  limitation='Final history never supplies earlier decisions; parallel quote mode is not bar finality or a trade timestamp.')
    # Never overwrite an earlier result or emit raw callback/account content.
    with Path(output).open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', required=True)
    parser.add_argument('--capture', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = diagnose(args.trace, args.capture, args.output)
    print(json.dumps({k: result[k] for k in ('expected_minutes', 'prospective_minutes',
                     'first_snapshot_differs_from_final', 'readiness')}))
