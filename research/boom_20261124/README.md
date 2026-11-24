# Big-move prediction upgrade — 2026-11-24 — verdict: NEGATIVE (the current model stays)

Target: |close − open| ≥ 0.75 m, the same definition as `range_alert/explosion.py`. Pre-open features only.
Selection on 2015–2019 by top-decile explosion rate (walk-forward); one final run on 2020–2026.

| Variant | Selection 2015–19: AUC / top-10% | **Test 2020–26: AUC / top-10% / rest** |
|---|---|---|
| Current: 11 features, logistic | 0.642 / 34.9% | **0.626 / 36.4% / 19.1%** |
| + calendar, logistic | 0.643 / 36.5% | — |
| + calendar + FOMC day, logistic | 0.646 / 35.7% | — |
| + calendar + FOMC, gradient boosting (selected) | 0.643 / 47.6% | 0.619 / 31.2% / 19.7% |

- The selected-minus-current top-10% difference has a 95% bootstrap CI of −11.6..+1.0 points. The 2015–2019 gain was overfit.
- Training 2009–2019: FOMC days explode 32.9% (n=82) vs 25.5% on other days. The effect is real but adds no ranking power.
- Current model top-10% by test year: 2020 42%, 2021 0%, 2022 44%, 2023 20%, 2024 9%, 2025 41%, 2026 12%, against base rates of 18/16/35/27/19/17/14%. It flags volatile **regimes**, and in calm years its flags are at or below the base rate.

FOMC dates: `fomc_dates.py` (federalreserve.gov, fetched 2026-11-24).

# After the first hour (10:30 NY) — verdict: VALIDATED, deployed as `range_alert/first_hour.py`
SPX hourly Dec 2023 – Nov 2026. Parameters fitted before 2025-01-01 (257 sessions). Test on 2025-01..2026-11-13 (461 sessions).
- Day high > first-hour high: train 67%, **test 64%**. Day low < first-hour low: 64% / **57%**. Both sides break: 31% / 24%.
- Extension levels (train quantiles, in m) and their test coverage: up q70 0.289 → **75%**, q90 0.594 → **95%**; down q70 0.294 → **74%**, q90 0.736 → **92%**.
- Big rest-of-day move (|close − 10:30| ≥ 0.5 m) by first-hour-range tercile (cuts 0.339 / 0.472 m): test **14% / 21% / 29%** (train 17 / 25 / 37).
Limits: only 3 years of hourly data, one regime split, and Yahoo index bars.

# First-hour direction → rest of day (SPY) — verdict: NEGATIVE (the sign flips between regimes)
Rule selected on 2024 (fade a first hour ≥ 0.3 m: 55% wins, +4.6 pt). On 2025–2026: 44% wins, −4.3 pt (CI −13.4..+4.8).
Following the first hour did better in 2025–2026 (best: +5.4 pt, CI −0.6..+11.5) but lost in 2024. No stable direction edge.
