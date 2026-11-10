# Failure analysis, random-timing baseline and validation sizing (2026-11-08)

Script: `failure_baseline.py` (seed 901, 500 draws) -> `failure_baseline.json`. Runs on the 116 CONSUMED sessions: descriptive, in-sample.
It does not change the decision (REJECT_CHANGE_KEEP_CONTROL) and tunes nothing.

## Why the recent block failed
| Block | Early matches by leg start, first 40m (control -> seeded) | Early flips gained / lost | Unmatched signals first-40m decision (control -> seeded) |
|---|---|---|---|
| older (78) | 1 -> 15 | 16 / 0 | 2 -> 42 |
| recent (38) | 4 -> 2 | 3 / 3 | 1 -> 27 |

The seed creates 27-42 extra signals in the first 40 minutes. In the older block they land on legs early; in the recent block almost none do.
Legs starting after minute 40 are unchanged (25 vs 25 older, 10 vs 10 recent). The gain is confined to the older, 5-minute-raw block.

## Baseline comparison: random decision times, same signal count, same 30m spacing, random side
| Metric (all 116) | Actual | Random mean [95% range] | Draws >= actual |
|---|---:|---|---:|
| control early (<=25% consumed) | 48 | 42.9 [33, 55] | 107/500 |
| seeded early | 64 | 52.6 [40, 65] | 23/500 |
| control matched (<=75% consumed) | 199 | 124.6 [110, 138] | 0/500 |
| seeded matched | 224 | 137.6 [123, 152] | 0/500 |
| no-signal baseline | 0 | 0 | - |

Per block, recent: control early 16 vs random 14.6 (191/500 >=); seeded early 16 vs 17.8 (360/500 >=).
Reading: both detectors identify legs after confirmation better than random timing (matched), but **their "early" matches are not distinguishable from random timing** in the recent block and only marginal for seeded overall. The early window (first 25% of a >=20-point leg) is wide, so the early metric is weak evidence by itself; lead time versus movement onset is still unproven.

## Validation size (corrected 2026-11-08; `sizing_clustered.py` -> `sizing_clustered.json`)
Earlier version used a linearized ratio formula and called the result "+/-5 pp at 55 sessions" without checking dependence. Re-derived with session-level and 5-session block bootstrap (4000 draws, seed 1101) on the 116 consumed sessions (365 legs, control early rate 13.2%).
Dependence found: session design effect 0.96 and lag-1 autocorrelation of session residuals -0.011, i.e. no detectable clustering or serial dependence in this sample (itself an estimate from 116 sessions; legs inside a session come from one retrospective segmentation).

| Sessions | 95% half-width, early RATE (session / block bootstrap) | half-width, seeded-minus-control RATE DIFFERENCE |
|---:|---|---|
| 20 | +/-8.2 / 7.8 pp | +/-6.2 pp |
| 30 | 6.8 / 6.6 | 5.0 |
| 54 | 4.9 / 4.9 | 3.6 |
| 80 | 4.1 / 3.9 | 3.0 |
| 116 | 3.4 / 3.2 | 2.4 |

Corrections: (1) the "+/-5 pp at ~54 sessions" holds only for the level of the early rate at p near 13%, under the sample's observed (weak) dependence; it is not the size needed to confirm an improvement. (2) The observed in-sample paired difference was +4.4 pp (selected sample; recent block 0), so a +/-3.6 pp interval at 54 sessions would only barely exclude zero if that effect were real; the earlier 71-session figure for 80% power stands, and a halved true effect needs far more. (3) Early matches were not distinguishable from random timing, so a rate interval alone is weak evidence; the excess over random has wider uncertainty (not computed here). Treat session counts as collection targets, not proof.
