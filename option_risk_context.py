"""Research context for long options; never an entry signal or a probability."""
from dataclasses import dataclass
from datetime import datetime
from math import isfinite


@dataclass(frozen=True)
class VolatilityObservation:
    # Values must already be normalized by an adapter with documented units.
    annualized_decimal: float
    underlying: str
    as_of: datetime
    source: str
    basis: str  # calendar_365 or trading_252
    horizon_days: float  # IV tenor / RV lookback, explicitly disclosed


def compare_volatility(iv, rv, *, now, max_age_seconds=60):
    result = {"status": "UNAVAILABLE", "research_only": True,
              "entry_signal": False, "reason": "missing_verified_volatility_metadata"}
    if iv is None or rv is None:
        return result
    if now.tzinfo is None or not isfinite(max_age_seconds) or max_age_seconds <= 0:
        raise ValueError("aware clock and positive finite age required")
    for value in (iv, rv):
        if (value.as_of.tzinfo is None or not value.source.strip()
            or not value.underlying.strip()
            or not isfinite(value.annualized_decimal) or value.annualized_decimal <= 0
            or not isfinite(value.horizon_days) or value.horizon_days <= 0
            or value.basis not in ("calendar_365", "trading_252")):
            return {**result, "reason": "invalid_volatility_metadata"}
        if not 0 <= (now - value.as_of).total_seconds() <= max_age_seconds:
            return {**result, "reason": "stale_or_future_volatility"}
    if iv.underlying != rv.underlying or iv.basis != rv.basis or iv.horizon_days != rv.horizon_days:
        return {**result, "reason": "incomparable_underlying_basis_or_horizon"}
    return {**result, "status": "OBSERVED", "reason": "historical_comparison_not_forecast",
            "iv_annualized": iv.annualized_decimal, "rv_annualized": rv.annualized_decimal,
            "iv_minus_rv_percentage_points": 100 * (iv.annualized_decimal - rv.annualized_decimal),
            "iv_to_rv": iv.annualized_decimal / rv.annualized_decimal,
            "basis": iv.basis, "horizon_days": iv.horizon_days,
            "iv_as_of": iv.as_of.isoformat(), "rv_as_of": rv.as_of.isoformat(),
            "iv_source": iv.source, "rv_source": rv.source}


def long_option_context(*, right, strike, underlying, ask, multiplier=100):
    """Expiry payoff arithmetic at ask, before fees; not intraday profit targets.

    Use only after the caller's independent underlying/book freshness gates.
    No expiry time, IV, delta, theta or vega is inferred from the strike/date.
    """
    if right not in ("C", "P") or multiplier != 100 or not all(
        isfinite(x) and x > 0 for x in (strike, underlying, ask)):
        raise ValueError("valid SPX long-option inputs required")
    otm = max(0., strike - underlying) if right == "C" else max(0., underlying - strike)
    breakeven = strike + ask if right == "C" else strike - ask
    move = breakeven - underlying if right == "C" else underlying - breakeven
    return {"research_only": True, "entry_signal": False,
            "otm_distance_points": otm, "otm_distance_pct": 100 * otm / underlying,
            "expiry_breakeven_before_fees": breakeven,
            "favorable_move_to_expiry_breakeven_points": move,
            "premium_at_ask_usd": ask * multiplier,
            "maximum_premium_loss_usd_before_fees": ask * multiplier,
            "volatility_comparison": {"status": "UNAVAILABLE",
                "reason": "missing_verified_volatility_metadata", "entry_signal": False},
            "expiry_time_status": "NOT_PROVIDED",
            "greeks_status": "NOT_PROVIDED",
            "profit_probability": None}
