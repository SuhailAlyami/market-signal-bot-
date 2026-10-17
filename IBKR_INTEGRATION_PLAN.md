# IBKR data integration for Suhail Hunter — stage 0 (read-only)

**Status:** not connected. No trade execution permission, passwords or broker API session stored in this repository.

## Why not connect IBKR directly to Render Free now?
IBKR's official TWS/IB Gateway requires the account owner to authenticate in its GUI; unattended headless login is unsupported. Client Portal Gateway also requires a daily browser reauthentication. Do not place account passwords, authentication cookies or session tokens in Render or GitHub. Render Free can sleep, so it cannot guarantee continuous streaming.

## Data plan to confirm inside IBKR Client Portal
- CME Real-Time L1 (ES/NQ futures): published non-professional price ~US$1.55/month.
- Cboe Streaming Market Indexes (SPX index): published ~US$3.50/month.
- OPRA L1 (SPX options): published ~US$1.50/month; network/bundle requirements, data fees, API entitlements and professional classification may change applicability.
- Quote subscriptions alone do not necessarily authorize external redistribution or automated use. Confirm market data entitlements and API access with IBKR before purchase.

Official references:
- https://brokerage.ibkr.com/en/pricing/market-data-pricing.php
- https://www.interactivebrokers.com/docs/tws-api/doc/architecture/the-trader-workstation/the-ib-gateway
- https://www.interactivebrokers.com/docs/web-api/authentication/cpgw/client-portal-gateway-faq

## Architecture when owner is ready
1. Run TWS/IB Gateway on **owner-controlled computer or a secured GUI-capable host**; authenticate interactively, with MFA. No credentials shared with ChatGPT.
2. Run a **read-only local feed adapter** adjacent to IB Gateway. Use IBKR's official API market data requests, explicitly resolve front-month futures contracts, and validate exchange-specific timestamps, entitlement errors, gaps, freshness, reconnects and session resets.
3. Move sanitized quotes/bars to a durable, access-controlled internal feed; no publicly exposed gateway socket. Verify exchange redistribution permissions before moving or sharing any raw quotes.
4. Implement source failover by **failing closed**: never label Yahoo delayed data as IBKR live; no SPX 0DTE recommendations when there are no verified live options bid/ask and IV data.
5. Benchmark against delayed-source pilot for at least 10 independent active sessions. Keep trade execution disabled.

## Current code
`ibkr_readiness.py` exposes a disabled-by-default, loopback-only socket readiness probe and contract metadata. A successful socket probe **does not** prove a logged-in trading session or a live data entitlement. It is NOT wired into the current signal detectors. `tests/test_ibkr_readiness.py` validates the safety gate.
