"""Evaluate only bars that were already closed when the snapshot was captured.

The frozen candidate is not refit. Alerts are research outbox records, never
orders. A GitHub cron after the cash close is not this loop.
"""
from datetime import timezone
import json
from pathlib import Path

from close_policy import closed_starts, is_closed_at_capture, parse_time

RIYADH_OFFSET_HOURS = 3


def riyadh(value):
    t = parse_time(value)
    shifted = t.astimezone(timezone.utc).replace(tzinfo=None)
    from datetime import timedelta
    local = shifted + timedelta(hours=RIYADH_OFFSET_HOURS)
    return local.strftime('%Y-%m-%d %H:%M:%S') + '+03:00'


def fresh_state(model_sha):
    return {
        'model_sha256': model_sha,
        'cooldown_trading_bars': 10,
        'resolved_bar_starts': [],
        'waiting_alignment': [],
        'alert_keys': [],
        'last_slot': None,
        'signals': [],
    }


def _index(bars):
    return {str(parse_time(bar['start'])): bar for bar in bars}


def evaluate(spx_bars, es_bars, spx_captured_at, es_captured_at, state, qualify, shadow=None):
    """qualify(bar, es_bar) -> None or a signal dict. shadow(signal) -> bool.

    Missing ES does not burn the SPX bar. A repeat of a resolved bar emits nothing.
    Low-quality bars do not consume cooldown.
    """
    if spx_captured_at is None or es_captured_at is None:
        raise ValueError('capture time required')
    spx_captured_at = parse_time(spx_captured_at)
    es_captured_at = parse_time(es_captured_at)
    state = json.loads(json.dumps(state))
    resolved = set(state['resolved_bar_starts'])
    spx = _index(spx_bars)
    es = _index(es_bars)
    closed = closed_starts(spx, spx_captured_at)
    alerts = []
    for start in closed:
        key = str(parse_time(start))
        if key in resolved:
            continue
        if not is_closed_at_capture(start, spx_captured_at):
            continue
        match = es.get(key)
        if match is None or not is_closed_at_capture(match['start'], es_captured_at):
            if key not in state['waiting_alignment']:
                state['waiting_alignment'].append(key)
            continue
        signal = qualify(spx[key], match)
        state['waiting_alignment'] = [item for item in state['waiting_alignment'] if item != key]
        state['resolved_bar_starts'].append(key)
        resolved.add(key)
        if signal is None:
            continue
        slot = int(signal['slot'])
        if state['last_slot'] is not None and slot - state['last_slot'] < state['cooldown_trading_bars']:
            signal = dict(signal, suppressed='COOLDOWN')
            state['signals'].append(signal)
            continue
        veto = bool(shadow(signal)) if shadow else False
        signal = dict(signal, shadow_veto=veto, provenance='RESEARCH_ONLY', notifications_are_orders=False)
        state['last_slot'] = slot
        state['alert_keys'].append(key)
        state['signals'].append(signal)
        # Experimental veto is recorded and does not delete the frozen comparison alert.
        alerts.append(signal)
    return state, alerts


def append_outbox(path, alerts):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a', encoding='utf-8') as handle:
        for alert in alerts:
            handle.write(json.dumps(alert, ensure_ascii=False, sort_keys=True) + '\n')
    return len(alerts)
