# Square-of-Nine levels on SPX — verdict: FAILURE

Protocol `protocol.json` committed in 1a1116a before any computation; one run (`gann.py` -> `results.json`), 4 unit tests pass.
Data: 113 SPX sessions with a preceding session in the previously consumed archive (2026-05-20..2026-11-04); sessions >= 2026-11-05 not used. Temporal split: development < 2026-09-14 (76 sessions), out-of-sample test 2026-09-15..2026-11-04 (37). Step S = sqrt(prior close)/2, median 43.9 points in the test block.

| Test block, cost 1 pt round trip | Gann Sq9 | Control: 0.5 x prior-day range | Control: random anchor, Gann step (200 draws) | No signal |
|---|---:|---:|---:|---:|
| Trades | 40 | 77 | - | 0 |
| Net points | -273.7 | +165.9 | median -36.7 (p5 -267.9, p95 +163.8) | 0 |
| Expectancy / trade | -6.84 (95% CI -12.13 to +0.25) | +2.16 | - | 0 |
| Max drawdown | 273.7 | 117.1 | - | 0 |
| Win rate | 20% | 46% | - | - |

At cost 0.5: -253.7; at cost 2: -313.7. Exits: 27 stop, 6 target, 7 session close. Rejection trades -207.3 (35), break trades -66.4 (5).
Gann net ranks at the 5th percentile of the random-anchor control (worse than 95% of random anchors) and is below the volatility control.
Development block (reported only): Gann -326.8 on 102 trades; volatility control -293.4.

Verdict by the preregistered rule: FAILURE (net <= 0 and below both controls). The positive volatility-control result in the test block is not a finding: it was negative in development, it was not the hypothesis, and these sessions were consumed by earlier research.
