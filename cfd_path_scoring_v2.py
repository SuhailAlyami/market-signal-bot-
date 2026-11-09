"""Independent reference for Pine's price-path adjudication; never a fill model."""
from math import isfinite


def outcome(direction, entry, scale, opening, high, low):
    if direction not in (-1, 1) or not all(isfinite(x) for x in (entry, scale, opening, high, low)):
        raise ValueError('invalid_inputs')
    if min(entry, scale, opening, high, low) <= 0 or not low <= opening <= high:
        raise ValueError('invalid_ohlc_or_scale')
    target = entry + direction*scale
    stop = entry - direction*.75*scale
    if direction*(opening-target) >= 0:
        return 'target'
    if direction*(opening-stop) <= 0:
        return 'stop'
    hit_target = high >= target if direction == 1 else low <= target
    hit_stop = low <= stop if direction == 1 else high >= stop
    if hit_target and hit_stop:
        return 'ambiguous'
    return 'target' if hit_target else 'stop' if hit_stop else 'pending'
