"""Capture-time bar completion, continuation veto, and pre-registered adoption.

Processing time must never promote a snapshot that was still forming when it
was captured. Adoption rules are fixed here so a later result cannot move them.
"""
from datetime import datetime, timedelta, timezone
import math

STEP = timedelta(minutes=5)
Z95 = 1.959963984540054


def parse_time(value):
    if value is None or value == '':
        raise ValueError('capture time required')
    t = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if t.tzinfo is None:
        raise ValueError('timezone required')
    return t.astimezone(timezone.utc)


def bar_end(start, step=STEP):
    return parse_time(start) + step


def is_closed_at_capture(start, captured_at, step=STEP):
    return parse_time(captured_at) >= bar_end(start, step)


def closed_starts(starts, captured_at, step=STEP):
    captured = parse_time(captured_at)
    return [start for start in starts if captured >= bar_end(start, step)]


def wilson(hits, n, z=Z95):
    if n <= 0:
        return None
    p = hits / n
    den = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return [(centre - margin) / den, (centre + margin) / den]


def continuation(side, return30):
    """Causal: sign of the already completed 30-minute return, not EMA/channel mid."""
    if return30 is None or not math.isfinite(float(return30)) or float(return30) == 0:
        return False
    return (float(return30) > 0 and int(side) == 1) or (float(return30) < 0 and int(side) == -1)


def adopt_filter(before_hits, before_scored, after_hits, after_scored):
    """One pre-registered decision. Never marks the book ready to trade."""
    if after_scored > before_scored or after_hits > before_hits or after_scored < 0:
        raise ValueError('filter must be a subset of the original signals')
    removed_hits = before_hits - after_hits
    removed_misses = (before_scored - before_hits) - (after_scored - after_hits)
    if removed_misses < 0:
        raise ValueError('filter accounting is not a subset')
    rate = (after_hits / after_scored) if after_scored else 0.0
    before_rate = (before_hits / before_scored) if before_scored else 0.0
    interval = wilson(after_hits, after_scored)
    # Point estimate may clear 70 percent while the interval still includes worse rates.
    # A research shadow is allowed only when the filter strictly improves the point
    # estimate, keeps at least eight scored events, and deletes fewer correct signals
    # than incorrect ones, with at most two correct deletions. Trading stays off.
    shadow = bool(
        after_scored >= 8
        and rate >= 0.70
        and rate > before_rate
        and removed_hits < removed_misses
        and removed_hits <= 2
    )
    claim = bool(interval is not None and rate >= 0.70 and interval[0] >= 0.70 and shadow)
    return {
        'shadow_research_candidate': shadow,
        'seventy_percent_claim_supported': claim,
        'trading_ready': False,
        'frozen_weights_changed': False,
        'rate': rate,
        'before_rate': before_rate,
        'wilson95': interval,
        'removed_hits': removed_hits,
        'removed_misses': removed_misses,
        'minimum_scored': 8,
        'max_removed_hits': 2,
    }
