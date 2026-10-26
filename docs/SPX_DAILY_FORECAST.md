# Daily SPX forecast v1 — 2026-10-26

Owner scope changes to next-session direction/high/low; no options recommendations.
Implementation: spx_daily.py, SQLite immutable forecasts + actual outcomes, Flask API/dashboard.
Research only; NOT_READY, no measured market advantage, no live deployment.

## Input and execution
Existing requirements.txt already includes Flask, numpy, pandas and pandas-market-calendars.
Input JSON: {"symbol":"SPX","security_type":"IND","source":"IBKR","bars":[{"date":"YYYY-MM-DD","open":0,"high":0,"low":0,"close":0}]}.
Replace placeholders with genuine positive native SPX daily RTH bars from the existing IBKR collector. At least81 consecutive NYSE sessions needed. Source fields are declarations, not cryptographic provenance: retain original capture/manifests. Never relabel proxies. This is a daily adapter contract, not the existing intraday raw format. Automatic broker-to-daily aggregation is NOT yet wired; the existing availability recorder is unchanged.

Run from repo root:

    python spx_daily.py --import-json PATH_TO_NATIVE_DAILY_JSON
    python spx_daily.py --serve

Dashboard http://127.0.0.1:5050/ ; GET /prediction/tomorrow ; GET /performance.
Use two processes for watcher and server:

    python spx_daily.py --import-json PATH_TO_NATIVE_DAILY_JSON --watch-seconds 300

Watcher reimports updated file, scores previous forecast after close, expands labeled analog library, and saves next session prediction. It does not acquire data or register an OS task. Default database .hunter-state/spx-daily.sqlite must be backed up; no cloud service or secrets. Localhost only. Collector/Windows installation not performed here.

NYSE calendar defines next session (not next calendar day), DST/holidays/early close. Reject missing sessions, incomplete OHLC, wrong declared asset, conflicting revisions. First target prediction cannot be overwritten. Scoring only for issue time before target open. GET never learns or creates forecasts, returns503 for missing/expired forecast. Target remains visible during its session; date/as_of/issued_at clarify validity.

## Frozen initial model and measurement
Version spx-daily-analog-v1. No parameter optimization performed. Features: body/range,5day trend,14day ATR,20day realized volatility, distance to20day support/resistance. Forty nearest historical examples using training-only feature standard deviation. Labels use next close minus previous close, sideways within0.1 source ATR; high/low median next-session excursions normalized by source ATR. Historical intervals use10th/90th analog quantiles, not guaranteed80% coverage. Direction ties use fixed Bullish,Bearish,Sideways order. This is a baseline, not a proven best model.
SPX index has no directly traded volume; volume_used=false. No invented volume or silent ES/SPY proxy. Volume integration requires separately identified data and a new protocol.

confidence=null until30 scored prospective same-direction predictions; then observed historical accuracy for that predicted class (not calibrated probability for this individual session). high_confidence/low_confidence similarly null until30 outcomes, then empirical interval coverage, not exact-price hit probability. analog_agreement is separate and never labeled confidence. No default82%.

DB retains date/issue/as_of/payload, Actual High/Low, Direction Accuracy, signed High/Low Error (predicted minus actual). Payload contains daily direction/high/low. Dashboard groups by target month, evaluated-only denominator, monthly directional hit rate, absolute high/low errors, cumulative average boundary error curve; empty states do not show fake success.

walk_forward(rows) provides fixed expanding-prefix DEVELOPMENT_ONLY diagnostic, separate from prospective calibration. It is NOT run on previously consumed data here. Next: preregister chronological split and baseline comparisons before untouched data; measure direction confusion matrix/baselines, high/low MAE, interval coverage and width, independent replication, then live shadow. All previous consumed cohorts remain consumed. No production alerts or qualification gates changed.

Validation:5 synthetic tests pass (prefix invariance, immutable issue/score/revision rejection, wrong asset/gaps/incomplete data rejection, NYSE weekend/early close, API empty state). No real predictive result, deployed endpoint, or current price forecast is claimed.
