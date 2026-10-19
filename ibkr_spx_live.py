"""Read-only IBKR TWS/IB Gateway SPX quote collector (operator's local machine).

Requires: pip install ib_insync
The owner must sign in to TWS/IB Gateway and subscribe to SPX index + OPRA.
No order placement, no secrets, no connection to remote broker sockets.
"""
from __future__ import annotations
import argparse
import json
import os
import math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ibkr_readiness import gateway_config
from spx_option_selector import OptionQuote, select_spx_0dte


def snapshot(direction: str, *, client_id: int = 81, timeout: float = 15) -> dict:
    if direction not in ("CALL", "PUT"):
        raise ValueError("direction must be CALL or PUT")
    config = gateway_config()
    if config is None:
        return {"status": "NOT_READY", "reason": "IBKR_DATA_ENABLED is not true"}
    try:
        from ib_insync import IB, Index, Option
    except ImportError:
        return {"status": "NOT_READY", "reason": "Install ib_insync on the local machine"}
    host, port = config
    ib = IB()
    index_ticker = None
    option_tickers = []
    try:
        ib.connect(host, port, clientId=client_id, readonly=True, timeout=timeout)
        ib.reqMarketDataType(1)  # Explicitly request live, not delayed.
        index = Index("SPX", "CBOE", "USD")
        qualified = ib.qualifyContracts(index)
        if not qualified:
            return {"status": "NOT_READY", "reason": "SPX index contract unavailable"}
        index = qualified[0]
        index_ticker = ib.reqMktData(index, "", False, False)
        ib.sleep(3)
        index_price = index_ticker.marketPrice()
        if index_ticker.marketDataType != 1 or not math.isfinite(index_price) or not 0 < index_price < 100000:
            return {"status": "NOT_READY", "reason": "Live SPX index quote not verified"}
        now = datetime.now(timezone.utc)
        expiry = now.astimezone(ZoneInfo("America/New_York")).strftime("%Y%m%d")
        if index_ticker.time is None or index_ticker.time.tzinfo is None or not 0 <= (now - index_ticker.time).total_seconds() <= 10:
            return {"status": "NOT_READY", "reason": "Stale or unverified SPX index timestamp"}
        chain_params = ib.reqSecDefOptParams("SPX", "", "IND", index.conId)
        chains = [c for c in chain_params if c.tradingClass in ("SPXW", "SPX") and expiry in c.expirations]
        if not chains:
            return {"status": "NOT_READY", "reason": "No verified SPX 0DTE expiry"}
        chain = next((c for c in chains if c.tradingClass == "SPXW"), chains[0])
        strikes = sorted((float(s) for s in chain.strikes if abs(s - index_price) / index_price <= 0.01), key=lambda s: abs(s-index_price))[:8]
        right = "C" if direction == "CALL" else "P"
        contracts = [Option("SPX", expiry, strike, right, "SMART", tradingClass=chain.tradingClass) for strike in strikes]
        contracts = ib.qualifyContracts(*contracts)
        if not contracts:
            return {"status": "NOT_READY", "reason": "No qualified SPX option contracts"}
        option_tickers = [ib.reqMktData(contract, "", False, False) for contract in contracts]
        ib.sleep(4)
        collected_at = datetime.now(timezone.utc)
        quotes = []
        for ticker in option_tickers:
            bid, ask = ticker.bid, ticker.ask
            if ticker.marketDataType != 1 or bid is None or ask is None:
                continue
            # TWS tickers do not expose an exchange-certified quote timestamp.
            # Do not mark snapshots as verified live solely because data type is 1.
            quote_time = ticker.time
            if quote_time is None or quote_time.tzinfo is None:
                continue
            quotes.append(OptionQuote(
                symbol="SPX", expiry=collected_at.astimezone(ZoneInfo("America/New_York")).date().isoformat(),
                right=right, strike=float(ticker.contract.strike), bid=float(bid), ask=float(ask),
                quote_time=quote_time, source="IBKR TWS live", live_verified=True))
        # The index ticker timestamp is required too; never invent freshness.
        index_time = index_ticker.time
        if index_time is None or index_time.tzinfo is None:
            return {"status": "NOT_READY", "reason": "Missing SPX index quote timestamp"}
        result = select_spx_0dte(quotes, direction=direction, underlying=float(index_price),
                                 underlying_time=index_time, now=collected_at, underlying_live_verified=True)
        if result is None:
            return {"status": "NOT_READY", "reason": "No fresh, narrow-spread live SPX option quotes",
                    "quotes_checked": len(quotes)}
        return {"status": "RESEARCH_ONLY", "contract": result.__dict__,
                "verified_live_type": True, "orders_enabled": False}
    except Exception as exc:
        return {"status": "NOT_READY", "reason": type(exc).__name__}
    finally:
        if ib.isConnected():
            if index_ticker is not None:
                ib.cancelMktData(index_ticker.contract)
            for ticker in option_tickers:
                ib.cancelMktData(ticker.contract)
            ib.disconnect()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--direction", choices=("CALL", "PUT"), required=True)
    args = parser.parse_args()
    print(json.dumps(snapshot(args.direction), ensure_ascii=False, default=str))
