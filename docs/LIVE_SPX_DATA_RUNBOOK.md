# SPX data connection: official IBKR MCP and legacy TWS

## Preferred route: official IBKR MCP (implemented)

Official server: https://api.ibkr.com/v1/api/mcp-public

The collector uses the official MCP Python SDK, OAuth authorization-code/PKCE,
and ONLY the `mcp.read` scope. The transport allowlist contains five market-data
tools; account queries, order instructions and order submission are rejected
before reaching the server. OAuth state lives outside the checkout with private
filesystem permissions, never in reports, logs, artifacts or source control.

### What was verified on 20 October 2026

- The owner's ChatGPT connector returned the SPX index, today's SPXW chain and
  actual CALL/PUT bid/ask snapshots successfully.
- Eight actual connector responses were replayed through `collect_spx`; four
  option books were collected. The index reported FROZEN. All four option
  feeds reported REALTIME but supplied no timestamp attached to bid/ask.
- The adapter therefore recorded the prices for research and correctly returned
  NOT_READY. The timestamp under `last` belongs to the last trade, not to bid/ask.
  No executable contract, forecast probability, order or option P&L was invented.
- Direct unauthenticated HTTP access to the official MCP endpoint returned 401
  and advertised OAuth metadata. Protected-resource metadata declares
  `mcp.read`, `mcp.write`, `mcp.orders.submit`; this client requests only the first.
- Independent runtime authorization is NOT completed. Connecting IBKR inside
  ChatGPT does not copy its private OAuth session to Render or GitHub Actions.

### Authorize a separate runtime

1. On an operator-controlled machine, install:
   `python -m pip install -r requirements.txt -r requirements-ibkr.txt`.
2. Run `python ibkr_mcp.py --authorize`. Open the emitted IBKR authorization URL
   in a browser on that same machine. A callback listens ONLY on
   `127.0.0.1:8765`; the SDK handles PKCE and state validation.
3. Authorize market-data reading. The application requests `mcp.read` only.
   Credentials are entered only at IBKR. Never paste OAuth tokens into a chat,
   issue, repository, workflow artifact or environment-variable printout.
4. The default private auth directory is
   `~/.local/share/suhail-hunter/ibkr`; `IBKR_MCP_AUTH_DIR` may select another
   private directory OUTSIDE the checkout. Use a persistent protected filesystem
   on the SAME runtime for unattended refresh.
5. Run `python ibkr_mcp.py` for one observation. Private quote report:
   `.hunter-state/ibkr_snapshot.json`. Console output contains only data-health
   metadata. A missing login returns `authorization_required` without opening
   a browser or attempting a background sign-in.

A local callback cannot be completed from an iPhone opening a callback on a
different host. A hosted mobile authorization UI has not been implemented or
deployed. Do not publish the loopback callback or OAuth files to work around
that. Hosted authorization and persistent secret storage remain a separate
deployment step; do not describe this route as running autonomously on Render.

### Application integration (reader starts by default; authorization required)

- Base `requirements.txt` includes the pinned `requirements-ibkr.txt` dependencies.
- The reader starts by default. Set `IBKR_MCP_ENABLED=false` to disable it explicitly.
- Missing independent OAuth state returns `authorization_required` without network
  requests, implicit sign-in, orders or notifications.
- Optional `IBKR_MCP_POLL_SECONDS` defaults to 60 and has a 60-second minimum.
- The existing app starts one bounded collector thread (90-second deadline).
- `/health` exposes an independent `ibkr` object: disabled, authorization_required,
  collected, error or stale_report. It does not expose quotes, account data,
  tokens, or authentication URLs. A stale report cannot imply current readiness.
- Yahoo research monitoring remains independent. No silent fallback between
  providers and no Telegram recommendation is enabled by this data connection.
- A candidate can reach the existing selector only when the index last-price
  timestamp AND an explicit bid/ask timestamp are fresh and REALTIME.
  Even then the output is RESEARCH_ONLY; strategy performance is unproven.
- Authenticating the runtime, measuring quote-update evidence, and validating
  an early detector out of sample remain required for product readiness.

Official references:
- https://www.interactivebrokers.com/en/trading/ai-integrations.php
- https://www.interactivebrokers.co.uk/en/general/about/mediaRelations/7-28-26.php
- https://api.ibkr.com/v1/api/mcp-public/.well-known/oauth-protected-resource
- https://api.ibkr.com/.well-known/oauth-authorization-server
- https://github.com/modelcontextprotocol/python-sdk

## Legacy alternative: TWS / IB Gateway

The existing local socket collector below remains available. Gateway is not
required for the official MCP route above.

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

