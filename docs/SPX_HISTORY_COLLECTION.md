# SPX historical acquisition: explicit daily windows

The connected history tool rejected a month of one-minute bars with
`Combination of period and step will provide more then allowed 1000 data points`.
Its exposed schema has no start/end cursor. Repeating a latest-window request
does not acquire older sessions. This is not evidence that a new subscription is
required.

`collect_spx_sessions.py` uses the existing local official IBKR TWS API instead.
It resolves SPX / IND / CBOE / USD and requires exactly one matching contract.
Every completed NYSE session has a different explicit UTC `endDateTime`, with
`durationStr="1 D"`, `barSizeSetting="1 min"`, `whatToShow="TRADES"`, `useRTH=1`,
`formatDate=2`, `keepUpToDate=False`. A normal session contains 390 expected
minutes; an early close is shorter. Sequential requests are separated by 16
seconds, timeout after 60 seconds and cancel their history subscription. It does
not retry a rejected request automatically. Maximum acquisition: 60 sessions.

Official references:
- https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars
- https://www.interactivebrokers.com/docs/tws-api/sync-doc/historical-market-data
- https://interactivebrokers.github.io/tws-api/historical_data.html

## Run on the computer hosting the already configured Gateway

Use the same Python environment and official `ibapi` installation used by the
existing `spx_primary.py`. Pandas and pandas-market-calendars are already declared
in this repository's requirements. Gateway must already be signed in with API
access enabled; this program does not log in or change Gateway settings. Keep
the Gateway API in read-only mode. It sends only contract-details and historical
data requests, cancellation and disconnect; no account, positions or order calls.

From the `research/spx-only-price-watch-20261022` branch:

```powershell
python collect_spx_sessions.py --end 2026-10-21 --sessions 20 --output .hunter-state/spx-history-20 --port 4001
```

4001 matches the existing primary launcher. Set `--port` to the port already
configured in your Gateway if different; no port scanning or setting changes.
Use a new output directory for each run. Client ID defaults to 20331025, separate
from the existing primary launcher. Twenty sessions take at least five minutes
plus response times. The end date deliberately excludes the consumed development
session of 2026-10-22. Do not change the frozen protocol's exclusion or split
rules to obtain a more favorable result.

## Outputs and failure behavior

Each day produces `.raw.json` (original ordered bars, server start/end strings,
exact request, contract identity and receipt time) and `.validated.json` (OHLC
session view plus exact coverage). Index volume, including unavailable `-1`, is
preserved as the SDK decimal's string only in raw data; it is not an input to the
SPX price-only detector. No volume is invented. `manifest.json` records raw SHA256,
missing minute timestamps and coverage. Identical duplicate rows are counted in
the validated view; conflicting duplicates or unordered bars reject the run.
No prices or timestamps are filled, interpolated or shifted. Raw observations
outside the requested NYSE session remain in the raw file and are counted but
excluded from its session view. Incomplete sessions remain explicitly incomplete.

Exit code 0 means every requested session has all expected minutes. Exit code 2
means acquisition failed or coverage is incomplete; it does not mean the detector
passed. An interrupted process may leave partial daily files without a final
manifest; these must not be treated as a complete dataset. A new directory avoids
mixing acquisitions. The 256 MiB free-space guard prevents starting another file
when storage is nearly exhausted. Provider error messages, authentication details
and account IDs are never persisted. Only a sanitized error code/reason is saved.

Do not interpret complete historical bars as verified live entitlement, exchange
arrival timestamps, latency measurements, options prices, or proof of an edge.
The collector neither evaluates the frozen train/validation/holdout study nor
turns on alerts. Dataset quality and model quality are separate gates. Quality
status stays NOT_READY until the frozen study passes on actual acquired history.

After successful capture, `evaluate_spx_sessions.py` can run the frozen
chronological study; see `docs/SPX_CHRONOLOGICAL_STUDY.md`. The evaluator independently
rechecks raw hashes and coverage, and leaves holdout outcomes uncomputed after
failed validation. It never enables alerts or orders.

## Verification status

Offline tests cover different daily UTC ends, NYSE Thanksgiving closure, early
close, DST, missing minutes, identical/conflicting duplicates, unchanged raw
volume, disconnect and mocked multi-day collection. These are synthetic transport
and integrity checks. No native Gateway connection or twenty-session market
acquisition has been executed from this cloud environment; the user's Windows
localhost is not accessible here.
