# Daily structure candidate v2 — 2026-10-26

Owner requests technical price-based daily direction/high/low plus eventual early expansion detection. This supersedes the v1 feature description in SPX_DAILY_FORECAST.md, not its provenance/deployment limitations.

Fixed before any market evaluation: same40analogs,ATR14,20session references and0.1ATR direction label; add close location, upper/lower wick rejection normalized by ATR, higher-high+higher-low / lower-high+lower-low structure, and failed20session high/low breaks. Previous20session breakout boundaries exclude the current session. These are descriptive inputs to learned historical outcomes, not automatic BUY/SELL rules or promises of liquidity causation. No volume invented.

spx_daily.forecast(rows) now identifies spx-daily-structure-v2; forecast(rows,structure=False) retains v1 baseline. Confidence and interval-coverage cohorts require this exact model version. Original forecasts are never overwritten even when model changes. Reference high/low are observed20session extremes, NOT predicted ceilings/floors or calibrated invalidation levels. Predicted high/low remain medians and intervals permit exceedance; no final-extreme guarantee.

No consumed market outcomes measured, no tuning, independent accuracy unknown. Next valid experiment must preregister new chronological train/validation/holdout dates before acquisition/outcomes and compare both versions with simple direction/range baselines. Preserve every result incl failures; do not select candidate by old cohorts. Existing complete prospective-trace wait unchanged. No notification promotion.

Eight synthetic tests (five daily plus three structure) cover prefix/future invariance, failed-break input, baseline separation and existing persistence/calendar/API checks. NOT_READY remains. No native daily feed adapter/Windows deployment or live endpoint claimed. Intraday session-conditioned revisions/expansion detection remain separate unfinished work; never merge ES/CFD overnight prices into cash SPX labels. Current change is code, not a market result.
