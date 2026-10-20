"""Grade observed premium states against subsequently received trade bars.

This is a shadow outcome, never a fill or a pre-movement prediction metric.
The horizon is the NEXT five FULL one-minute bars after actual detection.
"""
from datetime import datetime, timedelta, timezone
import json
import math
import os
from pathlib import Path


def aware(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('aware_outcome_clock_required')
    return result.astimezone(timezone.utc)


def outcome(event, records, now, *, horizon=5, max_arrival_delay=120):
    if now.tzinfo is None or now.utcoffset() is None or horizon < 1 or max_arrival_delay < 0:
        raise ValueError('invalid_outcome_parameters')
    detected = aware(event['detected_at'])
    if detected > now:
        raise ValueError('future_detection_time')
    price = event.get('reference_trade_price')
    if isinstance(price, bool) or not isinstance(price, (int, float)) or not math.isfinite(price) or price <= 0:
        raise ValueError('invalid_reference_trade_price')
    start = detected.replace(second=0, microsecond=0)
    if start < detected:
        start += timedelta(minutes=1)
    end = start + timedelta(minutes=horizon)
    result = {'event_id': event['event_id'], 'state': event['state'],
              'detected_at': event['detected_at'], 'evaluated_at': now.isoformat(),
              'window_start': start.isoformat(), 'window_end': end.isoformat(),
              'horizon_full_minutes': horizon, 'reference_trade_price': price,
              'status': 'pending', 'target_hit': None, 'max_trade_rise_pct': None,
              'max_trade_fall_pct': None, 'close_trade_change_pct': None,
              'execution_price': None, 'research_only': True, 'notifications_enabled': False}
    # Preserve the first received version, irrespective of archive iteration
    # order. Later revisions can never improve an earlier shadow outcome.
    first = {}
    contract_ids = set()
    for row in records:
        if (row.get('expiry') != event['expiry'] or row.get('side') != event['side']
                or float(row.get('strike', -1)) != float(event['strike'])):
            continue
        bar_start, received = aware(row['bar_start']), aware(row['received_at'])
        if not start <= bar_start < end or received > now:
            continue
        contract_ids.add(row['contract_id'])
        if bar_start not in first or received < aware(first[bar_start]['received_at']):
            first[bar_start] = row
    if len(contract_ids) > 1:
        return {**result, 'status': 'censored', 'reason': 'ambiguous_contract_identity'}
    expected = [start + timedelta(minutes=i) for i in range(horizon)]
    if now < end:
        return {**result, 'reason': 'outcome_window_not_complete'}
    if any(stamp not in first for stamp in expected):
        return {**result, 'status': 'pending' if now <= end + timedelta(seconds=max_arrival_delay) else 'censored',
                'reason': 'missing_future_bars'}
    rows = [first[stamp] for stamp in expected]
    for stamp, row in zip(expected, rows):
        values = [row.get(key) for key in ('open', 'high', 'low', 'close', 'volume')]
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
            return {**result, 'status': 'censored', 'reason': 'invalid_future_bar'}
        op, high, low, close, volume = values
        elapsed = (aware(row['received_at']) - stamp - timedelta(minutes=1)).total_seconds()
        if (min(op, high, low, close) <= 0 or volume <= 0 or high < max(op, close)
                or low > min(op, close) or high < low):
            return {**result, 'status': 'censored', 'reason': 'invalid_or_inactive_future_bar'}
        if (row.get('feed_status') != 'REALTIME' or row.get('historical_delayed') not in (None, 0, False)
                or not 0 <= elapsed <= max_arrival_delay):
            return {**result, 'status': 'censored', 'reason': 'late_delayed_or_unfinished_future_bar'}
    return {**result, 'status': 'scored', 'reason': 'first_received_trade_bars_not_executable_returns',
            'target_hit': max(row['high'] for row in rows) >= price * 1.25,
            'max_trade_rise_pct': 100*(max(row['high'] for row in rows)/price-1),
            'max_trade_fall_pct': 100*(min(row['low'] for row in rows)/price-1),
            'close_trade_change_pct': 100*(rows[-1]['close']/price-1)}


def reconcile(directory, now=None):
    """Single writer: grade unresolved observations and append terminal results.

    The output journal itself is the durable deduplication source, so restart
    after an append does not create duplicates. Corrupt input fails visibly.
    """
    now = now or datetime.now(timezone.utc)
    directory = Path(directory)
    journal = directory/'premium_shadow.jsonl'
    if not journal.exists():
        return {'scored': 0, 'censored': 0, 'pending': 0, 'target_hits': 0}
    output = directory/'premium_outcomes.jsonl'
    completed = {}
    if output.exists():
        for line in output.read_text().splitlines():
            item = json.loads(line)
            if item['event_id'] in completed:
                raise ValueError('duplicate_outcome_id')
            completed[item['event_id']] = item
    events = {}
    for line in journal.read_text().splitlines():
        event = json.loads(line)
        if event['state'] in ('WATCH', 'ACCELERATION'):
            events.setdefault(event['event_id'], event)
    unresolved = [event for key, event in events.items() if key not in completed]
    records = []
    # Read only UTC-date files intersecting unresolved future windows.
    wanted_dates = set()
    for event in unresolved:
        detected = aware(event['detected_at'])
        wanted_dates.update((detected.date().isoformat(), (detected+timedelta(minutes=6)).date().isoformat()))
    for date in wanted_dates:
        for path in (directory/'premium_bars').glob(f'*-{date}.jsonl'):
            records.extend(json.loads(line) for line in path.read_text().splitlines())
    pending, terminal = 0, []
    for event in unresolved:
        result = outcome(event, records, now)
        if result['status'] == 'pending':
            pending += 1
        else:
            terminal.append(result)
    if terminal:
        fd = os.open(output, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        with os.fdopen(fd, 'a') as stream:
            for item in terminal:
                stream.write(json.dumps(item, allow_nan=False)+'\n')
                completed[item['event_id']] = item
            stream.flush()
            os.fsync(stream.fileno())
    return {'scored': sum(item['status'] == 'scored' for item in completed.values()),
            'censored': sum(item['status'] == 'censored' for item in completed.values()),
            'pending': pending, 'target_hits': sum(item['target_hit'] is True for item in completed.values())}
