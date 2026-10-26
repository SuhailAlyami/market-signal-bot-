# Persistent daily research cycle

run_spx_daily.py joins the native daily collector to SQLite ingestion, previous
forecast scoring and immutable next-session forecast issuance. It does not alter
v2/v3 logic, calibration thresholds, the frozen 2025 experiment or production alerts.

A cycle chooses the last NYSE session closed for at least five minutes, using the
actual calendar close (DST and early closes included), and requests 252 consecutive
completed sessions through the existing local read-only Gateway path. A SQLite
reservation is committed BEFORE acquisition. The same source session is never
requested twice by this runner, including concurrent processes and restarts.
RUNNING reservations after a crash are left visible and not automatically retried.
Failures also consume this runner's one attempt per source session; it does not
reset any other collector budget or retry malformed historical data repeatedly.

After validating capture/input hashes, declared native identity, calendar and
OHLC, ingest scores only genuinely pre-session issued forecasts and preserves
their original payloads. Then issue creates a new research forecast only before
the target opens. Late captures may update outcomes but never fabricate backdated
forecasts. No file-based signal feed is silently substituted for cash SPX.

Files beneath state-dir:
- runs.sqlite: source session reservation, timestamp, status and full result;
- captures/YYYY-MM-DD: immutable raw, input and capture manifest;
- spx-daily.sqlite: original issued forecasts and scored daily outcomes.

On the actual Gateway host (not executed against the user's machine here):
```
python run_spx_daily.py --watch-seconds 300
```
Run the existing API separately against the SAME database:
```
python spx_daily.py --db .hunter-state/daily/spx-daily.sqlite --serve
```
The loop checks the calendar; broker acquisition occurs once per eligible source
session, not once per poll. It is an ordinary local process, not an installed
Windows service or registered task. It needs an awake machine and authenticated
Gateway. It has no notifications, option/order calls or automatic model promotion.
The status RESEARCH_FORECAST_ISSUED describes issuance, NOT forecast accuracy.
Model payload still says RESEARCH_NOT_VALIDATED. Empirical confidence rules remain
unchanged and synthetic test outcomes never populate a user's database.

Current blocked market evaluation remains WAIT_VALID_DATA because the two
connected IBKR daily exports disagree internally on five 2024/2025 OHLC rows.
This runner does not correct them or prove a successful live Gateway export.
The existing study must still pass unchanged independent evaluation and prospective
shadow replication. All new runner checks use offline fake captures.
