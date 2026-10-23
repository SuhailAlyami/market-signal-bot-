"""Research-only lifecycle correction; frozen v1 readiness rules are unchanged."""
import pandas as pd

from spx_inside_range import (CONFIRM_WINDOW, HOLD_MINUTES, PRIMARY,
                              _event, directions)

VERSION = 'spx-inside-range-lifecycle-v2'


def lifecycle_safe(frame):
    if (frame.index.tz is None or not frame.index.is_unique
            or not frame.index.is_monotonic_increasing):
        raise ValueError('aware_unique_ordered_index_required')
    readiness = directions(frame, PRIMARY)
    sessions = frame.index.tz_convert('America/New_York').date
    events, active = [], None

    def emit(index, state, side, reason):
        row = _event(frame, index, state, side, reason)
        row['rule_version'] = VERSION
        events.append(row)

    for index, timestamp in enumerate(frame.index):
        decision = timestamp + pd.Timedelta(minutes=1)
        side = int(readiness.iloc[index])
        valid = bool(frame.valid.iloc[index])
        continuous = (index > 0 and sessions[index] == sessions[index-1]
                      and timestamp-frame.index[index-1] == pd.Timedelta(minutes=1))
        if active is not None:
            phase, direction = active['phase'], active['direction']
            terminal = 'CANCEL' if phase == 'READINESS' else 'EXIT'
            reason = None
            if not valid or not continuous:
                reason = 'context_discontinuity'
            else:
                close = float(frame.close.iloc[index])
                broken = (close < active['invalidation'] if direction > 0
                          else close > active['invalidation'])
                original = int(frame.original_direction.iloc[index])
                if broken:
                    reason = 'invalidation_wick'
                elif phase == 'READINESS':
                    elapsed = (decision-active['decision']).total_seconds()/60
                    if side == -direction:
                        reason = 'opposite_readiness'
                    elif elapsed > CONFIRM_WINDOW:
                        reason = 'confirm_window_elapsed'
                    elif original == direction:
                        active.update(phase='CONFIRMATION', confirmed_at=decision)
                        emit(index, 'CONFIRMATION', direction, 'same_direction_break')
                    elif elapsed >= CONFIRM_WINDOW:
                        reason = 'confirm_window_elapsed'
                elif original == -direction:
                    reason = 'opposite_break'
                elif decision-active['confirmed_at'] >= pd.Timedelta(minutes=HOLD_MINUTES):
                    reason = 'hold_elapsed'
            if reason is not None:
                emit(index, terminal, direction, reason)
                active = None
            # Never cancel/exit and re-arm on the same completed bar.
            continue
        if valid and side:
            active = dict(phase='READINESS', direction=side, decision=decision,
                          invalidation=float(frame.low.iloc[index] if side > 0
                                             else frame.high.iloc[index]))
            emit(index, 'READINESS', side, PRIMARY)
    return events
