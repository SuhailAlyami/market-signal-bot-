# Missed-expansion diagnosis and next fixed hypothesis

All Sep1–15 native data in artifacts/independent_reversal are now **CONSUMED
DEVELOPMENT**, per user correction. Previous reports describe their historical
test status at the time, not permission to reuse them as independent evidence.
The Sep21–Oct18 proxy dataset is also consumed. New results cannot certify themselves.

## Development diagnosis BEFORE choosing modification

Replay trace and event causes:artifacts/missed_expansion_development.
Of223development events:213 have no early pre-level candidate;212 have no early
close in the narrow0.2ATR band at the prior20-minute boundary;104 movement
targets lie INSIDE that anchor20-minute range. Only9have an early setup still
waiting at onset;1has an early trigger rejected by strategy filters.122onsets
are within1–2minutes of anchor. Actual stage scoring:49setups detect4events early,
30triggers detect1early,1plan detects0early. Hence removing the second close
alone cannot repair coverage: the20-minute boundary restriction misses most
early opportunities. These are post-outcome diagnostic facts, not validation.

## One coherent modification, fixed before measuring it

`micro-range-5-v1`: target the preceding FIVE completed-minute high/low, rather
than the20-minute outer boundary. Five is the existing local contraction/trend
timescale, not the winner of a lookback search. Require existing contraction
previous5span/previous20span<=0.65, RVOL>=1.2, same5/15minute directional context,
and a directional completed candle closing >=0.1priorATR beyond the local edge.
Require its close in the outer directional quarter of its own high/low range;
this supplies closed-candle rejection protection instead of waiting two more
closes. No RVOL/trend/buffer threshold reduction, no future pivot/POC invention.

Fresh structural stop is one ES tick beyond BOTH opposite consolidation edge
and breakout candle extreme (min forlong/max forshort), not an old setupATR stop.
Reject wide risk; do not tighten the stop to fit. Existing common tick/entry/
max2ATR/1R+2R rules, warmup/gaps/session calendar,10minute lifetime/5minute cooldown
stay identical. Live freshness, actual option quotes, entry recheck and dedupe
remain outside strategy and unchanged. Production runtime is not changed yet.

## Evaluation and unused-data boundary

First run this one candidate on consumed Sep development for diagnostics; no
parameter fitting, grid or second variant is planned. Positive development
early-F1 versus current is necessary to justify spending independent requests;
development alone can never authorize live adoption. A failed development test
requires an explicit diagnosis/data-resolution decision, not a claimed completion.

Locked independent dates, NOT acquired/inspected when selecting these rules:
20sessions2026-07-20..2026-08-14, weekdays, native actualESU6/CME, same existing
read-only collector, one1D1minuteTRADES/RTH request perdate. No successful-link
rechecks, subscription purchase, account/order calls or live-reader restart.
Stop on substantive acquisition failure; no substituting development dates.
Use complete390barRTH sessions, no fill,31minute warmup,10minute edgeembargo,
same frozen223-style event definition (actual new event count derived later).
Earlier-period independence is not prospective/live or SPX-option proof.

Acceptance is unchanged from the preceding independent protocol: >=30scored
signals,>=5complete sessions, precision>=.50, Wilson95lower>=.40,
early-eventrecall>=.20,falsealarms/session<=2,medianlead>=1minute; positive lower95
paired-session early-F1 gain (5000draws,seed20261022) over current, nonnegative
point gain under+1minute availabilitydelay. All requested20sessions must pass
source coverage. No label/metric change to make local breakouts look better.
Report global event coverage even though strategy focuses on compression.

If accepted, update Python production and full matching Pinev6 with focused
safety/parity checks before current-service rollout. If not accepted, do not
call the task achieved or select current by default; report what remains
unexplained and any specific data-resolution/permission/time requirement.
