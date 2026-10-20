# Actual connected IBKR processing cycle — 2026-10-20 08:38 UTC

This is actual market data returned through the user's connected read-only IBKR
market-data tools, not a synthetic fixture. Both December 2026 CME futures
snapshots returned REALTIME. The retained chart responses contain 1001 rows;
the incomplete minute was removed before detection, leaving 1000 completed bars.

The canonical Hunter runtime accepted both streams at actual processing time
08:38:26.061691 UTC (11:38:26 Asia/Riyadh). Last-trade ages were approximately
12 seconds for ES and 19 seconds for NQ. Latest completed-bar age was 26 seconds.
The heartbeat was `ok`. No candidate events were generated. New York had not
opened. Empty events do not prove or disprove predictive accuracy.

Files retain the actual raw tool responses, processing report, canonical
heartbeat journal and SHA256 manifest. No account balances, orders or OAuth
credentials were queried or exported. A verification helper rejects the same
saved inputs as stale when processed later; it cannot backdate a new detection
to the saved quote timestamp.

The connected assistant performed this acquisition; a GitHub-hosted collector
was not independently authorized by this capture. Continuous external operation
must be verified separately. The connection-check workflow inspects actual
GitHub runner configuration and, only when a runner is configured, checks that
host's private authorization and current market data. It does not export chat
credentials or pretend a missing host is connected.
