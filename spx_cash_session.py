"""SPX cash RTH calendar; local receipt times never imply an open cash session."""
from datetime import timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

NY = ZoneInfo('America/New_York')
RIYADH = ZoneInfo('Asia/Riyadh')


@lru_cache(maxsize=16)
def _schedule(day):
    # NYSE cash RTH includes holidays, early closes and US DST.
    return mcal.get_calendar('NYSE').schedule(start_date=day, end_date=day+timedelta(days=14))


def cash_session(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('aware_clock_required')
    schedule = _schedule(now.astimezone(NY).date())
    active = schedule[(schedule.market_open <= now) & (now < schedule.market_close)]
    future = schedule[schedule.market_open > now]
    if active.empty and future.empty:
        raise RuntimeError('cash_calendar_unavailable')
    current = active.iloc[0] if not active.empty else None
    next_open = future.iloc[0].market_open if not future.empty else None
    return {'calendar': 'NYSE cash RTH', 'timezone': 'Asia/Riyadh',
            'is_open': current is not None,
            'open_riyadh': current.market_open.tz_convert(RIYADH).isoformat() if current is not None else None,
            'close_riyadh': current.market_close.tz_convert(RIYADH).isoformat() if current is not None else None,
            'next_open_riyadh': next_open.tz_convert(RIYADH).isoformat() if next_open is not None else None,
            'preopen_context': 'ES research only; not live cash SPX'}


def cash_active(now):
    return cash_session(now)['is_open']
