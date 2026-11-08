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

## Validation size from event counts (control early-match rate p = 13.2%, 3.15 legs/session, session-clustered)
| Target | Sessions |
|---|---:|
| 95% half-width of early rate +/-10 pp | 14 |
| +/-7.5 pp | 24 |
| +/-5 pp | 54 |
| At 20 sessions (~63 legs): half-width | +/-8.2 pp |
| 80% power for seeded gain of 0.138 early/session (paired sd 0.415) | 71 |
| same, if the true gain is half that | 284 |

20 sessions is therefore a first look at rate precision (+/-8 pp), not enough to confirm a change of the observed size; plan for ~55 sessions for precision and >=70 for the paired comparison.
The effect size comes from the sample that selected the change (winner's curse; recent-block gain was 0), so these are lower bounds on the work needed.
