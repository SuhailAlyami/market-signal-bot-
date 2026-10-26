# Close-only daily direction experiment — preregistered 2026-10-26

This is a NEW research target, not a repair or pass of the blocked OHLC study.
Original OHLC rules, dates, outcomes, v2/v3, forecasts and gates stay unchanged.
No more market acquisition. Use the retained native IBKR SPX IND TWO_YEARS
response, and corroborate its close column against the retained FIVE_YEARS
response. Agreement of two exports from the same provider is repeatability, NOT
independent price verification. Errors in highs/lows do not establish whether the
close column is correct. All metrics are conditional on this retained close series.

Exact window 2024-10-28..2025-12-31, all sessions retained. Validate complete NYSE
calendar and equal source array lengths, aware daily timestamps, finite positive
closes and matching native request identity. Strictly no high, low, open, volume,
ATR, candle/range features or extrema forecasts. Do not claim a complete OHLC
record or use this study to unlock high/low predictions.

Direction definition: next close versus current close, Bullish above +0.1%,
Bearish below -0.1%, Sideways within inclusive +/-0.1%. This differs from the
existing ATR-based daily target and must NEVER be compared as if identical.
No production classifier, confidence or issued forecast is replaced.

Candidate fixed before outcome evaluation: ridge least-squares three-class
scores, lambda=10, intercept unpenalized. Features: 1/3/5/10/20-day close return,
5/20-day return volatility, close-to-SMA20 distance, trailing 20-day drawdown.
Scale by training-only mean/std (zero std -> 1); clip normalized values +/-5.
Use the last <=252 completed labeled examples; min 40. No class balancing,
threshold search, feature selection or parameter tuning. Ties fixed Bullish,
Bearish,Sideways. Scores are not calibrated probabilities; confidence stays null.

Training prefix >=81 sessions. Validation 2025-04-01..2025-06-30; holdout
2025-07-01..2025-12-31 is evaluated ONLY after validation passes. Walk forward:
append actual prior-session outcomes but never the forecast session's outcome.
Baselines: expanding majority, prior-session direction, five-session momentum.
For BOTH validation and holdout require >=60 targets, all actual classes,
balanced accuracy >=45%, accuracy >=5 percentage points above EVERY baseline,
positive lower bound of a paired 95% bootstrap gain using 2000 resamples and
fixed seed 20261026. Keep all predictions and confusion matrices. No discretionary
exceptions; failed validation leaves holdout unevaluated. IID bootstrap is only
an initial gate, not independence proof. Even passing -> SHADOW_REQUIRED, never
READY, due to missing independent data replication/prospective outcomes.

Publish model code, protocol, input hashes, exact dates, counts and ALL outcomes.
A failure consumes validation for this hypothesis; no retuning/re-running on it
and claiming independence. Range study stays WAIT_VALID_DATA regardless.
