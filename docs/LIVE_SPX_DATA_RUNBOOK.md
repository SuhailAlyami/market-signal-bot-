# Live SPX 0DTE data — verified connection procedure

## Selected lawful route: IBKR TWS / IB Gateway

No free public endpoint has been verified to provide licensed, real-time SPX option NBBO reliably. The Yahoo ES/NQ research proxy and the TradingView SPX500 chart **are not SPX options quotes**. Do not switch to delayed data silently.

Official IBKR market data documentation:
- https://www.interactivebrokers.com/docs/tws-api/doc/quick-start/requesting-market-data
- https://www.interactivebrokers.com/docs/tws-api/doc/market-data-delayed/introduction
- https://www.interactivebrokers.com/docs/general/market-data-subscriptions/popular-market-data-subscriptions/introduction
- https://www.interactivebrokers.com/en/pricing/market-data-pricing.php

IBKR distinguishes live type 1 from delayed type 3. Required permissions for this path are generally **Cboe Streaming Market Indexes (SPX)** and **OPRA (US Options Exchanges)**, subject to account eligibility, API acknowledgement and any package prerequisites. Do not subscribe or spend money without the owner's approval.

## Owner-controlled local machine, not Render

1. Sign into TWS or IB Gateway using your own credentials and MFA; do not share credentials.
2. In TWS, enable API socket clients in settings. Use **read-only API** and a loopback socket, and note the configured port (Gateway paper commonly 4002; TWS paper commonly 7497; verify your installation).
3. Install Python packages locally: `python -m pip install ib_insync`.
4. In the shell, set `IBKR_DATA_ENABLED=true` and `IBKR_GATEWAY_PORT=<your-local-port>`. Host defaults to 127.0.0.1; non-loopback is deliberately rejected.
5. Run `python ibkr_spx_live.py --direction CALL` or `--direction PUT` during SPX options trading hours.
6. Expected result is either `RESEARCH_ONLY` with an observed strike/bid/ask/quote time, or `NOT_READY` with a reason. **Never** interpret `NOT_READY` as permission to fabricate a price.
7. Confirm in TWS that the underlying and option subscriptions explicitly allow API live streaming. Market data type 1 is necessary but not proof of a guaranteed exchange-to-screen latency. The adapter also checks quote timestamps and rejects stale data.

This is **read-only**; it does not place orders, forward credentials, or automatically send recommendations. It has not been tested against the owner's authenticated live gateway. Render cannot open a socket to a gateway on the owner's localhost.

## Acceptance test

- Both index and options have valid fresh timestamps and marketDataType=1.
- The same strike, expiry, bid and ask are visible in TWS.
- No alerts or trade suggestions when a quote is stale, missing, delayed, zero bid, crossed or too wide.
- Compare several actual observed timestamps with TWS across at least ten sessions; measure latency and out-of-sample option P&L after spreads, fees and slippage.
- No real-money orders without a separate explicit decision and safeguards.

## Alternatives assessed

Cboe DataShop 1-minute option quote interval files are delayed ~15 minutes; unsuitable for 0DTE early alerts. Cboe All Access API has a limited trial but live OPRA options prices require separate licensed market data. No scraping or unauthorized redistribution.
