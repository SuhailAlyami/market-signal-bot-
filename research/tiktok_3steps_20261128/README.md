# TikTok "3 steps" (1H liquidity sweep -> 15M confirmation -> 5M order block, R:R 1:2): FAILED

Owner sent a short video on 2026-11-28. Rules were made mechanical before running (see the `sweep3.py` docstring). Data: Dukascopy US500 1m,
2025-01..2026-11, 463 sessions, regular hours. Cost 0.5 pt round trip (median risk 6 pts).

| | n | win | avg R | 95% CI |
|---|---|---|---|---|
| rule 2025 | 178 | 26% | -0.37 | [-0.55, -0.20] |
| rule 2026 | 145 | 23% | -0.47 | [-0.66, -0.28] |
| opposite direction | 281 | 31% | -0.19 | [-0.34, -0.03] |
| random entries (same risk, 2R) | 330 | 35% | -0.12 | [-0.27, +0.02] |
| rule, target = 1H candle extreme | 323 | 20% | -0.56 | [-0.70, -0.42] |

Worse than random in both years. Not adopted, no alerts. Same conclusion as the earlier ICT/SMC test (sweep, FVG).
