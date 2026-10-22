"""SPX-only OHLC hypotheses. No volume proxy, companion symbol or option advice.

Fixed before development replay: 20-bar sweep/reclaim and 3-bar direct break.
These are unvalidated WATCH conditions, not a market-edge assertion.
"""
import math
from functools import lru_cache
import pandas as pd

VERSION = 'spx-price-watch-v1'


def observe(bars, index):
    result = {'version': VERSION, 'candidate': None, 'readiness': 'NOT_READY',
              'notify_eligible': False, 'volume_used': False, 'support_symbol': None}
    def reject(reason):
        return {**result, 'reason': reason}
    if type(index) is not int or index < 30 or index >= len(bars):
        return reject('insufficient_history')
    if bars.attrs.get('symbol') != 'SPX' or bars.attrs.get('security_type') != 'IND':
        return reject('native_spx_required')
    window = bars.iloc[index-30:index+1]
    if (not isinstance(window.index, pd.DatetimeIndex) or window.index.tz is None
            or not window.index.is_unique or not window.index.is_monotonic_increasing
            or any(t.second or t.microsecond for t in window.index)
            or not window.index.to_series().diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all()):
        return reject('invalid_or_missing_minute')
    try:
        rows = [tuple(float(row[k]) for k in ('Open', 'High', 'Low', 'Close'))
                for _, row in window.iterrows()]
    except (KeyError, TypeError, ValueError):
        return reject('invalid_prices')
    if any(not all(math.isfinite(v) and v > 0 for v in r)
           or r[1] < max(r) or r[2] > min(r) for r in rows):
        return reject('invalid_prices')
    prior, current = rows[-21:-1], rows[-1]
    atr = sum(max(rows[i][1]-rows[i][2], abs(rows[i][1]-rows[i-1][3]),
                  abs(rows[i][2]-rows[i-1][3])) for i in range(10, 30))/20
    if atr <= 0:
        return reject('zero_prior_atr')
    o, h, l, c = current
    hi, lo = max(r[1] for r in prior), min(r[2] for r in prior)
    local_hi = max(r[1] for r in rows[-4:-1])
    local_lo = min(r[2] for r in rows[-4:-1])
    sweep_up, sweep_down = l < lo < c, h > hi > c
    result.update(reference_high=hi, reference_low=lo, local_high=local_hi,
                  local_low=local_lo, prior_atr=atr, price=c)
    if sweep_up and sweep_down:
        return reject('ambiguous_two_sided_sweep')
    side, kind, level = 0, '', None
    if sweep_up and c > o:
        side, kind, level = 1, 'SWEEP_RECLAIM', lo
    elif sweep_down and c < o:
        side, kind, level = -1, 'SWEEP_RECLAIM', hi
    elif c > local_hi and c > o:
        side, kind, level = 1, 'LOCAL_BREAK', local_hi
    elif c < local_lo and c < o:
        side, kind, level = -1, 'LOCAL_BREAK', local_lo
    if not side:
        return reject('no_sweep_reclaim_or_local_break')
    # Actual current-bar structure, never an inferred fill or option stop.
    invalidation = l if side > 0 else h
    result['candidate'] = {'direction': side, 'price': c, 'atr': atr,
                           'level': level, 'invalidation': invalidation,
                           'rvol': None, 'kind': kind, 'rule_version': VERSION}
    return {**result, 'reason': kind.lower()}


def candidate(bars, index):
    return observe(bars, index)['candidate']


def market_open(now):
    return _session_open(now)


def _session_open(now):
    if now.tzinfo is None:
        raise ValueError('aware_clock_required')
    day = pd.Timestamp(now).tz_convert('America/New_York').date()
    schedule = _schedule(str(day))
    return bool(not schedule.empty and schedule.iloc[0].market_open <= now < schedule.iloc[0].market_close)


@lru_cache(maxsize=8)
def _schedule(day):
    import pandas_market_calendars as mcal
    return mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day)
