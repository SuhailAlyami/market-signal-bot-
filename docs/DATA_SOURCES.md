# Data availability and latency review — Issue #16

Reviewed on 2026-10-19 using public provider documentation. No account was opened,
subscription purchased, API entitlement enabled, or order submitted. These are
documentation findings; they are **not measured live-feed performance**.

## What is usable without a new subscription?

| Source | Documented scope / limitation | Decision for Suhail Hunter |
| --- | --- | --- |
| Yahoo Finance / existing `yfinance` requests | Yahoo's [exchange coverage table](https://help.yahoo.com/kb/SLN2310.html) lists CME data with a 10-minute delay. Historical bars can also be incomplete, revised, missing, or unavailable. An ES/NQ futures proxy is not a verified contract-specific exchange feed. | Retain only for underlying research and shadow WATCH observations, with completed-bar timestamps and freshness checks. Never label it real time. A recent timestamp alone cannot establish that the underlying prices were published promptly. |
| CME public delayed quotes | The exchange's [delayed quotes documentation](https://www.cmegroup.com/market-data/browse-data/delayed-quotes.html) states that equity-index futures quotes are delayed by at least 10 minutes. The page separately advertises real-time market-data products. | Public delayed quotes cannot provide the required early ES/NQ observation stream. No public quote scraping or subscription activation was added. |
| Alpaca Basic | The [market-data plan documentation](https://docs.alpaca.markets/us/docs/about-market-data-api) describes free real-time equities coverage from IEX only, rather than consolidated US exchanges. Free options use an indicative feed. The [options data documentation](https://docs.alpaca.markets/us/docs/historical-option-data) says indicative quotes are derived rather than actual OPRA quotes, and trades are delayed by 15 minutes. Account authentication is required. | A future independently configured Basic account could supply a timely **IEX-only SPY/QQQ research feed**; this is not ES/NQ futures or consolidated equity volume. No credentials were requested and no connection was claimed. Indicative options cannot unlock executable SPX guidance. |
| Alpaca index options | Current [index-options documentation](https://docs.alpaca.markets/us/docs/index-options) includes SPX/SPXW and places option-contract market data on the existing OPRA feed. It does not include underlying spot-index market data at initial launch. Access and market-data entitlements are separate questions. | Do not claim Alpaca categorically lacks SPX contracts; equally, contract support does not prove that this repository has a legitimate live SPX options chain. No such chain was verified. |
| Databento | Its [pricing page](https://databento.com/pricing/) offers finite signup credits for historical data and describes live licensing/subscriptions. The [getting-started guide](https://databento.com/docs/getting-started/build-first-app) also documents account/API setup. | Historical credits are a possible limited research resource, **not an ongoing free real-time feed**. No signup, payment details, credit consumption, or subscription was requested. Historical replay would still need point-in-time availability assumptions. |
| Cboe public SPX delayed-quote dashboard | The [SPX dashboard](https://www.cboe.com/delayed_quotes/spx/quote_table) identifies itself as delayed and expressly prohibits automated extraction of its quote table. Only the public page's documentation was reviewed; no option table was downloaded. | Exclude this dashboard as an automated data source. Delayed displayed quotes cannot verify a live executable SPX 0DTE chain. |
| Existing IBKR readiness helper | [IBKR's API market-data documentation](https://www.interactivebrokers.com/docs/general/market-data-subscriptions/introduction) states that most securities require Level 1 subscriptions for API data. `ibkr_readiness.py` only checks an opt-in local socket and provides contract-planning metadata. | A successful socket probe proves a listening port, not authentication, entitlement, contract resolution, exchange timestamps, or live quotes. Remain unverified. No paid package or local credentials were requested. |

**Finding:** this review did not identify or verify an already accessible,
credential-free, ongoing free source for genuinely timely ES/NQ plus a live SPX
option chain. It did identify a limited potential free IEX equity research path;
that is a different instrument and market-coverage scope. There is no basis to
enable SPX strike, premium, fill, or P&L claims.

## Measuring freshness without inventing latency

For every successful fetch, preserve `requested_at`, `received_at`, provider,
symbol, interval, the newest raw bar timestamp, and the newest **completed** bar
start/end. Record timezone and whether provider timestamps label the start or
end of the interval. Exclude the still-forming bar before measuring freshness or
running detection. Preserve failures too; an HTTP response or empty frame is not
a healthy feed.

Use separate quantities:

- **HTTP duration:** `received_at - requested_at`; this measures the request,
  not market-data publication latency.
- **Completed-bar age:** `received_at - completed_bar_end`; this is the age of a
  timestamped observation when received. Closed sessions, scheduled breaks,
  holidays, and stale or absent responses must be identified separately.
- **Provider publication latency:** when the event/bar first became available
  from that provider relative to its exchange event/end time. A one-off
  historical download does not measure this. Historical bar timestamps do not
  provide historical publication/arrival times.
- **Decision age:** `decision_at - completed_bar_end`; this also includes poll
  interval, request time, and computation/scheduler delay. A 5-minute bar already
  waits for its interval to complete even with a prompt provider.

To estimate actual availability, collect a rate-limited forward series during
active sessions and record the first receipt of each new completed bar. Compare
the same resolved instrument with a legitimately entitled independent stream if
one is already available. Report the sampling interval and clock uncertainty:
polling only brackets first availability and does not yield exact exchange
latency. Checking two delayed sources against each other does not establish
either as real time. Never shift old Yahoo bars forward or back to manufacture
lead time.

Repository fetch artifacts are **historical/freshness observations only** unless
they contain this forward arrival evidence. A detector evaluated on those bars
can report event-time out-of-sample research results; it cannot claim that an
alert would have arrived before the movement or before option premiums changed.
Leave `live_feed_verified` false and alerts for experimental variants off.

## Consequence for acceptance

Software tests can verify stale-feed rejection, completed candles, timestamps,
provider failure handling, and notification behavior. They cannot demonstrate
predictive advantage or certify source latency. Untouched out-of-sample event
metrics, their uncertainty, and a forward shadow record are separate evidence.
Until both detection quality and actual arrival timing are verified, the product
remains **NOT READY** for actionable SPX 0DTE recommendations.
