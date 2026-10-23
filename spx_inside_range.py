"""Causal SPX readiness while price is still inside the prior 3-bar range.

This is a research state machine, not an alert or an order. Constants are the
already published close-location cut and the structural complement of
``LOCAL_BREAK``: a bar that has already left that range is a confirmation, not
an early warning. No threshold here is a fitted quantile.
"""
import pandas as pd

from research_spx_premove import features as premove_features
from spx_price_watch import observe

VERSION = 'spx-inside-range-v1'
# Same close-location cut already frozen on slope_projection. Not refit.
CLOSE_LOCATION = 0.60
CONFIRM_WINDOW = 3
HOLD_MINUTES = 10
COOLDOWN_MINUTES = 10
PRIMARY = 'inside_range_pressure'
BASELINES = ('original_candidate', 'last_body', 'no_signal')
MODELS = (PRIMARY, *BASELINES)
ARABIC = {
    'READINESS': 'استعداد',
    'CONFIRMATION': 'تأكيد',
    'CANCEL': 'إلغاء',
    'EXIT': 'خروج',
}


def features(bars):
    """Session-local columns. Current bar is excluded from prior 3-bar levels."""
    frame = premove_features(bars)
    labels = bars.index.tz_convert('America/New_York').strftime('%Y-%m-%d')
    frame['prior_high3'] = float('nan')
    frame['prior_low3'] = float('nan')
    frame['bar_range'] = float('nan')
    frame['high'] = float('nan')
    frame['low'] = float('nan')
    ambiguous = pd.Series(False, index=bars.index)
    for _, group in bars.groupby(labels, sort=False):
        frame.loc[group.index, 'prior_high3'] = group.High.shift(1).rolling(3).max()
        frame.loc[group.index, 'prior_low3'] = group.Low.shift(1).rolling(3).min()
        frame.loc[group.index, 'bar_range'] = group.High - group.Low
        frame.loc[group.index, 'high'] = group.High
        frame.loc[group.index, 'low'] = group.Low
        for offset in range(len(group)):
            if observe(group, offset)['reason'] == 'ambiguous_two_sided_sweep':
                ambiguous.loc[group.index[offset]] = True
    frame['ambiguous'] = ambiguous.to_numpy()
    return frame


def directions(frame, model):
    if model not in MODELS:
        raise ValueError('unknown_inside_range_model')
    out = pd.Series(0, index=frame.index, dtype=int)
    if model == 'no_signal':
        return out
    if model == 'original_candidate':
        return frame.original_direction.astype(int).where(frame.valid, 0)
    if model == 'last_body':
        up = frame.valid & (frame.body > 0)
        down = frame.valid & (frame.body < 0)
    else:
        quiet = frame.valid & ~frame.ambiguous & (frame.bar_range <= frame.atr)
        up = (quiet & (frame.close <= frame.prior_high3) & (frame.original_direction != 1)
              & (frame.body > 0) & (frame.move3 > 0) & (frame.close > frame.previous_close)
              & (frame.position >= CLOSE_LOCATION))
        down = (quiet & (frame.close >= frame.prior_low3) & (frame.original_direction != -1)
                & (frame.body < 0) & (frame.move3 < 0) & (frame.close < frame.previous_close)
                & (frame.position <= 1 - CLOSE_LOCATION))
    up = up.fillna(False).astype(bool)
    down = down.fillna(False).astype(bool)
    out.loc[up & ~down] = 1
    out.loc[down & ~up] = -1
    return out


def signal_schedule(frame, model):
    """Fixed cooldown from the decision clock. Outcomes never choose the next bar."""
    signals, until = [], None
    for index, (timestamp, side) in enumerate(directions(frame, model).items()):
        decision = timestamp + pd.Timedelta(minutes=1)
        if side and (until is None or decision >= until):
            signals.append(dict(index=index, direction=int(side),
                                detected_at=decision.isoformat(), model=model,
                                rule_version=VERSION, notify_eligible=False))
            until = decision + pd.Timedelta(minutes=COOLDOWN_MINUTES)
    return signals


def _event(frame, index, state, direction, reason):
    decision = frame.index[index] + pd.Timedelta(minutes=1)
    return dict(index=index, state=state, arabic=ARABIC[state], direction=int(direction),
                detected_at=decision.isoformat(), reason=reason, rule_version=VERSION,
                notify_eligible=False)


def lifecycle(frame):
    """Readiness, confirmation, cancel and exit. One pass, no future bar."""
    events, active = [], None
    readiness = directions(frame, PRIMARY)
    for index, side in enumerate(int(value) for value in readiness.to_numpy()):
        if active is not None:
            close = float(frame.close.iloc[index])
            broken = close < active['invalidation'] if active['direction'] > 0 else close > active['invalidation']
            original = int(frame.original_direction.iloc[index])
            if active['phase'] == 'READINESS':
                if original == active['direction']:
                    active['phase'] = 'CONFIRMATION'
                    active['confirm_index'] = index
                    events.append(_event(frame, index, 'CONFIRMATION', active['direction'], 'same_direction_break'))
                elif broken or index - active['index'] >= CONFIRM_WINDOW or side == -active['direction']:
                    reason = ('invalidation_wick' if broken else
                              'opposite_readiness' if side == -active['direction'] else
                              'confirm_window_elapsed')
                    events.append(_event(frame, index, 'CANCEL', active['direction'], reason))
                    active = None
            elif (broken or original == -active['direction']
                  or index - active['confirm_index'] >= HOLD_MINUTES):
                reason = ('invalidation_wick' if broken else
                          'opposite_break' if original == -active['direction'] else 'hold_elapsed')
                events.append(_event(frame, index, 'EXIT', active['direction'], reason))
                active = None
        if active is None and side:
            invalidation = float(frame.low.iloc[index] if side > 0 else frame.high.iloc[index])
            active = dict(phase='READINESS', index=index, direction=side, invalidation=invalidation)
            events.append(_event(frame, index, 'READINESS', side, PRIMARY))
    return events


def strict_early_slots(event, bars):
    """Completed minutes at/after the anchor whose END is strictly before wick onset.

    When the anchor bar's end equals onset, the returned list is empty. No
    later completed bar, of any duration, can be both after that anchor decision
    and strictly before onset.
    """
    onset = pd.Timestamp(event['onset_time'])
    slots = []
    for index in range(event['anchor_index'], event['target_index']):
        if bars.index[index] + pd.Timedelta(minutes=1) < onset:
            slots.append(index)
    return slots


def gap_minutes(event):
    onset = pd.Timestamp(event['onset_time'])
    anchor_decision = pd.Timestamp(event['anchor_time']) + pd.Timedelta(minutes=1)
    return (onset - anchor_decision).total_seconds() / 60
