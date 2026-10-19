"""Research-only four-leg SPX put-spread payoff evaluator.

Two verticals: bull put credit spread + bear put debit spread.
All legs same expiration and multiplier. Prices are per index point.
No live prices, order execution, or claims of statistical edge.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from math import isfinite

@dataclass(frozen=True)
class Leg:
    strike: float
    right: str
    side: str
    premium: float
    multiplier: int = 100

def evaluate(legs: list[Leg], expiry: date, today: date, *,
             fee_per_contract: float = 0.0) -> dict:
    if len(legs) != 4 or not 40 <= (expiry-today).days <= 60:
        raise ValueError("Four legs and 40-60 DTE required")
    if not isfinite(fee_per_contract) or fee_per_contract < 0:
        raise ValueError("Invalid fee")
    for leg in legs:
        if (leg.right != "P" or leg.side not in ("BUY", "SELL")
            or leg.multiplier != 100
            or not all(isfinite(x) for x in (leg.strike, leg.premium))
            or leg.strike <= 0 or leg.premium < 0):
            raise ValueError("Invalid leg")
    sells = sorted((l for l in legs if l.side == "SELL"), key=lambda x: x.strike)
    buys = sorted((l for l in legs if l.side == "BUY"), key=lambda x: x.strike)
    if len(sells) != 2 or len(buys) != 2:
        raise ValueError("Two long and two short puts required")
    # Pair explicitly by strike ordering to avoid ambiguous duplicate legs.
    if len({l.strike for l in legs}) != 4:
        raise ValueError("Distinct strikes required")
    def payoff(spot: float) -> float:
        return sum((1 if l.side == "BUY" else -1) *
                   (max(l.strike-spot, 0)-l.premium)*100 for l in legs) - 4*fee_per_contract
    credit = sum((1 if l.side == "SELL" else -1)*l.premium for l in legs)*100 - 4*fee_per_contract
    # Piecewise-linear payoff extrema occur at strikes or at zero / above all strikes.
    spots = [0.0, *sorted(l.strike for l in legs), max(l.strike for l in legs)+1]
    outcomes = [(s, round(payoff(s), 2)) for s in spots]
    return {"status": "RESEARCH_ONLY", "dte": (expiry-today).days,
            "net_credit_after_fees": round(credit, 2),
            "max_profit": max(p for _,p in outcomes),
            "max_loss": min(p for _,p in outcomes),
            "payoff_knots": outcomes,
            "no_stop_is_not_risk_free": True,
            "requires_historical_option_quotes_for_backtest": True}
