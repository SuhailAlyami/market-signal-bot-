# IBKR-only market data migration — 2026-10-20

All active project history requests now use `ibkr_market_data.py` and the
existing official IBKR MCP OAuth transport. There is no yfinance import or
runtime dependency and no automatic secondary market-data provider. Removed
an unrelated CoinGecko fallback that manufactured OHLC ranges from price points.
The archived Yahoo raw datasets, old reports and historical reproduction
requirements keep their original labels; they are not relabeled as IBKR data.

## Runtime behavior

- Resolve exact US security types; ES futures can never select Eversource ES.
- Resolve and sort the actual futures expiry ladder, select the front nonexpired
  native CME contract. This is an explicit front-expiry rule, not a claim of
  choosing the most liquid contract around rollover.
- Runtime requests require REALTIME status, last-trade age at most 60 seconds,
  undelayed history when a delay flag is present, and latest completed bar age
  at most 120 seconds for minute bars (bar interval plus 60 seconds for larger
  bars). Missing fields, errors, frozen/delayed snapshots, invalid
  OHLCV, naive timestamps and incomplete bars do not reach runtime detectors.
- A realtime snapshot does not measure historical bar publication latency;
  receipt timestamps remain separate. Bid/ask freshness is never inferred from
  last-trade timestamps. No order or account-write tool is used.
- Canonical and NY runtime minute requests use a bounded 1000-bar window. Longer
  research period requests use exact supported chart periods; provider limits
  are errors, never a silently shortened study or fabricated pagination.
- Explicit research-only history requests do not require an open-market snapshot
  and never certify realtime delivery. Native IBKR OHLCV are not synthesized or
  adjusted merely because an older scanner passes `auto_adjust=True`.
- Native expiry futures differ from continuous Yahoo futures; old fitted models
  remain experimental. New-source performance requires new measured validation.
- Canonical state and NY first-receipt state use new IBKR filenames, avoiding
  mixing old-source scenarios or first-seen bar values into the new stream.

## Scope

Canonical Hunter, NY intraday journal, after-close replay, Asia/Globex and
SPY/QQQ watchers, the older bot history accessor, exploratory research and
acquisition use the same IBKR adapter. Four-week acquisition is no longer
claimed through a chart API without date pagination. Acquisition writes bounded
IBKR snapshots with actual coverage metadata. Legacy `ES=F` / `NQ=F` inputs are
aliases resolved to IBKR futures, never Yahoo requests.

PR CI uses offline historical fixtures, not a private brokerage login or a
Yahoo download. Retained old-study reproduction remains offline and unchanged.

## Observed checks, not claims of autonomous deployment

The connected assistant resolved December 2026 ES and NQ native CME contracts
and obtained 1001 actual minute bars per 1000-bar request from the exposed chart
API. NQ's snapshot returned REALTIME. ES's snapshot returned a provider internal
error during that check. Both raw history responses lacked an explicit delayed
flag. These observations do not certify every instrument or an external host.

The standalone runtime preflight currently returns AUTHORIZATION_REQUIRED.
ChatGPT's connected session is not an exported OAuth credential for GitHub.
No code path tries to recover or copy ChatGPT/Grok session tokens.

## Concrete activation path

On the machine that will run the collector or a trusted GitHub self-hosted runner:

```bash
python -m pip install -r requirements.txt
python ibkr_mcp.py --authorize
python ibkr_feed_preflight.py
python cloud_scan.py
python ny_intraday_shadow.py
```

The existing read-only OAuth command opens an IBKR authorization link and uses
a loopback callback on that same machine. The owner signs in on IBKR, never in
chat. OAuth files stay outside the repository, caches and uploaded artifacts.
The setup requires that host's successful OAuth registration/consent; neither
this patch nor a ChatGPT connection proves that registration succeeded.

For a self-hosted GitHub runner with that private authorization, set repository
variable `IBKR_RUNNER` to its dedicated runner label. The default remains
`ubuntu-latest`; an unauthenticated host reports AUTHORIZATION_REQUIRED in its
artifact and job summary and skips market scans. It does not falsely report a
working feed. No external runner is created or assumed by this change.

The hosted five-minute GitHub schedule remains best effort. Replacing the data
provider does not establish continuous first-minute capture or predictive edge.
Alerts remain OFF. An authorized collector host and new prospective market
validation are still required.
