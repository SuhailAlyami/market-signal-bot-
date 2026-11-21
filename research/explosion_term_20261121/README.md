# Explosion model + VIX term structure (2026-11-21)

Target unchanged: |close-open| >= 0.75 m. Walk-forward: each year 2020-2026 predicted by a model fit only on earlier years
(data from 2011, when VIX9D starts). Five variants fixed before running (`exp.py`, Yahoo daily ^GSPC ^VIX ^VIX9D ^VIX3M ^VVIX ^SKEW).

| variant | OOS AUC | top-decile explosion rate |
|---|---|---|
| current (11 features) | 0.609 | 32.5% |
| + VIX9D/VIX, VIX/VIX3M | 0.637 | 36.7% |
| + those + VVIX + SKEW | 0.638 | 36.7% |
| gradient boosting (base / all) | 0.598 / 0.621 | 31% / 30% |

Base rate 21% (n=1,681). Bootstrap 95% CI of the AUC gain (term vs current): [+0.013, +0.046].
Per year the gain is not uniform: better in 2020, 2022-2024; AUC lower in 2025-2026 (top decile 2026: 25% vs 14%).
Retrained model (through 2026-11-20): OOS AUC 0.643, top decile 36% vs 19% for the rest.
Does NOT fix the misses: 2026-11-16, -19, -20 all still 'normal' (p 0.28-0.29). Modest, statistically real improvement only.
