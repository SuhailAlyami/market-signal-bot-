# Defined-risk SPX put credit spread (modelled prices) — verdict: INCONCLUSIVE

Protocol fa2b668 committed before computing; one run; 2 unit tests pass. 442 non-overlapping 21-trading-day cycles 1990-2026. Prices are Black-Scholes with sigma = VIX (no skew), not real fills.

| Cost 2 pts/spread | Cycles | Win | Mean net | Total | Worst | Max DD | 95% CI mean |
|---|---:|---:|---:|---:|---:|---:|---|
| SELL, full | 442 | 75% | +0.95 | +421.9 | -154.4 | 307.0 | -0.48 to +2.22 |
| BUY same spread (old project's side) | 442 | 7% | -4.95 | -2,189.9 | -31.5 | 2,195.8 | - |
| SELL 1990-1999 | 121 | 31% | -0.23 | -27.7 | -12.7 | 106.5 | -0.67 to +0.17 |
| SELL 2000-2009 | 120 | 88% | -0.96 | -114.6 | -43.3 | 176.6 | -2.76 to +0.57 |
| SELL 2010-2022 | 155 | 92% | +1.22 | +189.6 | -154.4 | 290.3 | -1.82 to +3.63 |
| SELL 2023-2026 | 46 | 94% | +8.14 | +374.6 | -129.1 | 129.1 | +0.12 to +14.55 |

Cost 4: SELL full -1.05 per cycle (-462.1 total); 2023-2026 +6.14 (CI -1.88 to +12.55). Worst cycles: 2020-03-05 (-154.4), 2025-02-07 (-129.1), 2024-07-09 (-91.1).

Verdict (preregistered): INCONCLUSIVE — full-period mean positive but CI includes 0, and two blocks are negative.
Clear finding: buying the spread lost in 93% of cycles (-4.95 per cycle), consistent with the volatility premium.
Limitations: fixed point costs penalise the low-price 1990s far more than recent years (a protocol design flaw, kept, not changed after results); no skew (real OTM put credits are higher); recent-block edge rests on 46 cycles with single losses of 90-130 points.
