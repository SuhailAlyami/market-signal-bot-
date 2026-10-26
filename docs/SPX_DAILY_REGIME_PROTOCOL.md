# Daily regime challenger: frozen research protocol (2026-10-26)

Purpose: forecast the NEXT cash NYSE SPX session before its opening. Never infer
cash prices from overnight ES or unspecified SPX500 CFD charts. No option orders.

Freeze candidate v3 before market evaluation: v2 price structure plus ATR5/ATR20
compression, EMA20/EMA50 spread, EMA20 slope, three-day return acceleration and
opening gap, all normalized by trailing ATR. Robust median/IQR scaling from
training only; nearest 40 completed next-session labels, exponential distance
weights, weighted median extrema. No current/future outcomes in input features.
The candidate remains separate from the issued v2 forecast and cannot overwrite it.

Minimum 81 training sessions, 60 chronological validation and 60 holdout sessions.
CLI requires explicit validation and holdout start dates; no random split. Training
expands after each complete outcome. Select nothing on test. Evaluate v1, v2,
v3 and naive baseline on identical sessions. Naive predicts trailing majority
class and last-close +/- half trailing ATR. Neutral band stays +/-0.1 prior ATR.

Gate: candidate must beat BOTH v2 and naive by >=5 percentage points direction
accuracy, positive lower 95% paired-bootstrap bound on accuracy improvement,
balanced accuracy >=45% with all three actual classes represented, combined
high/low MAE at least 5% better and neither individual MAE worse. Validation
failure leaves holdout outcomes unopened by the evaluation routine. Holdout
passing still means SHADOW_REQUIRED, not proven generalization or alert enable.
No repeated tuning against this holdout; after any inspection it is consumed.
Keep per-session failures as well as successes, input SHA256 and exact date bounds.

Real market evaluation pending: available local minute histories span about 20
sessions, below the 201 daily-session minimum. Synthetic tests establish causality
and gate behavior only. No subscriptions, price feeds or live alerts are changed.

## Acquisition plan frozen before daily-history request
Request at most one TWO_YEARS / ONE_DAY IBKR SPX IND history, regular hours.
Resolve identity from the existing native contract evidence (416904, CBOE).
Use only sessions through 2025-12-31 for the first experiment, validation from
2025-04-01 and holdout from 2025-07-01. Reject missing sessions or insufficient
history; do not shift dates to obtain a pass. Data from 2026 is excluded from this
experiment, since parts of 2026 have already been inspected in intraday studies.
Acquisition may return no usable data; record that without inventing outcomes.

## Observed acquisition result
The bounded IBKR request returned 499 daily bars. The predeclared experiment
slice contains 295 sessions (2024-10-28 through 2025-12-31), no calendar gaps,
but five impossible OHLC rows: 2024-12-12 close below low; 2024-12-24,
2025-01-23, 2025-02-18 and 2025-06-12 close above high. Preserve the raw response
and request in artifacts/spx_daily_regime_20261026/raw.json, normalized slice in
input_2025.json, exact offending rows in data_audit.json. Evaluation result is
WAIT_VALID_DATA, holdout_evaluated=false. No direction accuracy or price error
can be reported for this experiment. No price corrections, deletions or date
shifts were applied. The original pending-data paragraph above describes the
pre-acquisition state. Next step is a consistent native daily export from the
local official API, rather than silently reconciling conflicting OHLC.

Reproduce (refuses report overwrite):
```
python evaluate_spx_daily.py --input artifacts/spx_daily_regime_20261026/input_2025.json --validation-start 2025-04-01 --holdout-start 2025-07-01 --output new-result.json
```
Existing v2 remains the issued model. V3 is a candidate for next-session daily
direction/range, not an evaluated minute-level explosion detector. Analog class
weights are NOT calibrated confidence; confidence stays null. The paired
bootstrap in this initial gate resamples individual days and does not establish
independence or replace a future replication/shadow study.

## Source reconciliation follow-up (before any model outcomes)
One additional native IBKR IND daily request with FIVE_YEARS is permitted solely
to test whether the malformed daily export is reproducible across request
windows. Keep all model rules and the original 2025 validation/holdout dates.
Restrict the evaluation slice to the SAME 2024-10-28..2025-12-31 dates. Never
replace individual prices, merge rows from responses, or omit bad sessions.
Save the second raw export separately and compare shared-date OHLC and validity.
If malformed again, do not retry; prepare the official local API acquisition path.

## Reconciliation outcome and direct Gateway path
The single FIVE_YEARS request returned 1,252 bars. Its original experiment slice
is identical to the TWO_YEARS response, including all five invalid OHLC rows.
See reconciliation_raw.json and reconciliation_audit.json; no further connector
retries or provider-price corrections were made. Predictive evaluation is blocked.

Added collect_spx_daily.py, using the existing local read-only Gateway reader.
It resolves SPX/IND/CBOE/USD identity, makes ONE 2 Y / 1 day / TRADES / RTH request
with an explicit end time and yyyyMMdd daily dates, preserves raw data and hashes,
and only emits input.json after native OHLC and consecutive calendar validation.
No sorting, deduplication, fills or silent repairs. Invalid input preserves raw
and WAIT_VALID_DATA manifest; output directories and reports cannot be overwritten.

On the Windows machine with the authenticated Gateway running on localhost:4001:
```
python collect_spx_daily.py --start 2024-10-28 --end 2025-12-31 --output artifacts/spx-daily-native-2025 --evaluate-protocol
```
The optional switch automatically runs the SAME frozen experiment only after a
validated capture; raw/input hashes are verified first. It does not update the
issued forecast model, send Telegram, register a scheduled task or place orders.
This cloud coding environment is not the user's Windows/Gateway host: direct
acquisition was tested with an offline fake reader only, NOT executed against the
user's PC, and no valid replacement data or predictive accuracy is claimed.

Official request/date-format references:
- https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars
- https://interactivebrokers.github.io/tws-api/historical_bars.html
