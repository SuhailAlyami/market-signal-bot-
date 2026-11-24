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
