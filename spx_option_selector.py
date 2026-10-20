"""Fail-closed SPX 0DTE quote selection. Research only; no broker orders.

The caller must supply *verified real-time* quotes from a licensed feed.
This module never synthesizes prices, expiry, or strike from index candles.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from zoneinfo import ZoneInfo
from option_risk_context import VolatilityObservation, compare_volatility, long_option_context

NY = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class OptionQuote:
    symbol: str
    expiry: str
    right: str
    strike: float
    bid: float
    ask: float
    quote_time: datetime
    source: str
    live_verified: bool
    multiplier: int = 100
    implied_volatility: VolatilityObservation | None = None
    realized_volatility: VolatilityObservation | None = None


@dataclass(frozen=True)
class Candidate:
    symbol: str
    expiry: str
    right: str
    strike: float
    bid: float
    ask: float
    mid: float
    spread_pct: float
    underlying: float
    observed_at: str
    source: str
    research_only: bool = True
    risk_context: dict | None = None


def select_spx_0dte(
    quotes: list[OptionQuote],
    *,
    direction: str,
    underlying: float,
    underlying_time: datetime,
    now: datetime,
    underlying_live_verified: bool,
    max_age_seconds: float = 10,
    max_spread_pct: float = 0.15,
    max_moneyness_pct: float = 0.01,
) -> Candidate | None:
    """Select nearest liquid ATM option; None means NOT READY, not 'no trade'.

    All clocks must be aware. Underlying and option quotes must be fresh and
    explicitly verified live by the feed adapter. No synthetic quotes.
    """
    if direction not in ("CALL", "PUT"):
        raise ValueError("direction must be CALL or PUT")
    if now.tzinfo is None or underlying_time.tzinfo is None:
        raise ValueError("timezone-aware clocks required")
    if (not isfinite(max_age_seconds) or max_age_seconds <= 0
        or not isfinite(max_spread_pct) or not isfinite(max_moneyness_pct)
        or not 0 < max_spread_pct < 1 or not 0 < max_moneyness_pct < 1):
        raise ValueError("invalid selection thresholds")
    if not underlying_live_verified or not isfinite(underlying) or underlying <= 0:
        return None
    age = (now - underlying_time).total_seconds()
    if not 0 <= age <= max_age_seconds:
        return None
    date = now.astimezone(NY).date().isoformat()
    right = "C" if direction == "CALL" else "P"
    accepted = []
    for q in quotes:
        if q.symbol != "SPX" or q.expiry != date or q.right != right:
            continue
        if (not q.live_verified or not isinstance(q.source, str)
            or not q.source.strip() or q.quote_time.tzinfo is None):
            continue
        age = (now - q.quote_time).total_seconds()
        if not 0 <= age <= max_age_seconds:
            continue
        if q.multiplier != 100 or not all(isfinite(x) for x in (q.strike, q.bid, q.ask)):
            continue
        if q.strike <= 0 or q.bid <= 0 or q.ask < q.bid:
            continue
        if abs(q.strike / underlying - 1) > max_moneyness_pct:
            continue
        mid = (q.bid + q.ask) / 2
        spread = (q.ask - q.bid) / mid
        if spread > max_spread_pct:
            continue
        accepted.append((abs(q.strike - underlying), spread, -q.bid, q))
    if not accepted:
        return None
    q = min(accepted, key=lambda item: item[:3])[3]
    context = long_option_context(right=q.right, strike=q.strike, underlying=underlying, ask=q.ask)
    if all(v is None or v.underlying == q.symbol for v in (q.implied_volatility, q.realized_volatility)):
        context["volatility_comparison"] = compare_volatility(
            q.implied_volatility, q.realized_volatility, now=now, max_age_seconds=max_age_seconds)
    return Candidate(
        symbol=q.symbol, expiry=q.expiry, right=q.right, strike=q.strike,
        bid=q.bid, ask=q.ask, mid=round((q.bid + q.ask) / 2, 4),
        spread_pct=round((q.ask - q.bid) / ((q.bid + q.ask) / 2), 4),
        underlying=underlying, observed_at=q.quote_time.isoformat(), source=q.source,
        risk_context=context,
    )

