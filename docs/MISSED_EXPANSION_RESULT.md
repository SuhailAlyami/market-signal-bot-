# Continued missed-opportunity investigation: NOT_READY

This continues PR38; it does not stop because the first alternative failed.
All September and previously used proxy observations are now development.
The twenty locked July20-Aug14 sessions have not been acquired or inspected.
No production detector, alert gate, Pine script or monitor was replaced.

## Diagnosis and hypotheses frozen before measurement

Of 223 consumed development events, 212 lack an early near-20minute-boundary
candidate, 104 have a target inside the original 20minute range, and 122 start
within one or two minutes of their anchor. Boundary coverage and observation
delay dominate; removing risk filters cannot manufacture earlier information.

Native five-second observations were genuinely newly acquired for the same
ten consumed sessions: 54,000 rows, complete cash-session coverage, unchanged
independent movement labels and conservative target deadline. Source hash:
`5704e0a957c7d0b8a6e67902304a7cc15ec4ddb0c5e99d6a51821630a8886346`.
Event onset is the START of the first positive-volume five-second touch. Both
baseline and alternatives use the same refined timing; coarse onset remains
audit-only. A minute-close timestamp must not create artificial early lead.

| Development candidate | Scored signals | Matches | Early /223 | Precision | False/session | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Frozen original continuation | 1 | 1 | 0 | 100% on one signal | 0 | -1.833m |
| Intrabar sweep, reset every minute | 83 | 11 | 9 | 13.25% | 7.2 | +0.25m |
| Intrabar sweep, frozen state across minutes | 133 | 36 | 11 | 27.07% | 9.7 | -0.167m |

Five-minute completed-bar breakout also failed: ten scored plans, zero early;
even before risk rejection its 94 scored raw triggers contain only one early
event. The intrabar continuation pilot has seven scored/four matched/zero early
on the consumed September2 pilot (not comparable as a full ten-day result).

The carry amendment addresses an actual structural defect: erasing an unfinished
sweep on a wall-clock minute boundary. Original range/ATR and the FIRST sweep
clock remain frozen, expiry ten minutes, no extension at a new extreme. Stops
remain behind actual structure and must satisfy the unchanged risk gate.
Protocol/code commit BEFORE its performance run:
`7a5bd81cae176e5141ff14a69054837a0ae63a4d`.

Carry precision Wilson95 is [20.24%,35.18%], early recall4.93%. Better movement
coverage does not offset its false alarms and poor early coverage. Positive
paired intervals on DEVELOPMENT are not independent validation. Both models
fail the pre-existing precision50%/Wilsonlower40%/earlyrecall20%/medianlead1m/
falsealarms<=2/session gates. The original is not accepted by default.

No extra confirmation filter on the fixed original sweep signal list could
raise its early-event recall above 9/223. The failure calls for a justified
change in information/coverage, not an arbitrary stricter or looser threshold.
The carry repair tests that coverage hypothesis but is insufficient itself.

## Further evidence needed, without invented blockers

The supplied reference treats a sweep as confluence, not a standalone entry;
these experiments are explicit limited models, not a certified full PDF setup.
Its price-level-volume models have not been tested. Candle volume cannot supply
actual volume-at-price or aggressor flow. Two bounded historical availability
requests succeeded: 1004 trade ticks covering28seconds, and1004 bid/ask ticks
covering8seconds. These are source feasibility samples, NOT session-level
training/validation or evidence of an edge. There is no newly established
permission/subscription blocker and no subscription was purchased.

Testing an anchored volume hypothesis would require defining its rules first,
then collecting complete bounded trade windows across development sessions,
with exchange/arrival timestamps, actual price/size, coverage and pacing checks.
This has not been silently launched as a large tick-history backfill. C drive
had approximately1.45GB free at inspection; any recorder needs a hard quota and
reserved free space. Do not delete user files. Do not promise a matching Pine
port for broker-only fields unavailable to TradingView.

## Verification and operational limits

Six targeted sweep/carry correctness tests passed: original behavior, distinct
later closes, actual wick stop, cross-minute original context, gap invalidation,
future independence, timeout and ambiguous/nontrading rejection. Both negative
full-development reports are rejected BEFORE any independent acquisition opens
a network connection. Prior successful infrastructure tests were not repeated.

The running monitor and sender configuration were preserved; no notification
test, deployment, order or Gateway restart was performed for this research.
Last operational proof remains the earlier saved evidence, not a new live claim.
The improvement objective is NOT COMPLETE. No validated Pine update is due yet.
