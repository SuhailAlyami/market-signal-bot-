# Fixed comparison protocol — before viewing results

Question: does a single programmable model from PDF pages1–6 improve actual
eligible TRIGGER plans over the running hunter-rolling20-v2, not just SETUP counts?
One model only; no parameter search or post-result changes.

Candidate `amd-reclaim-v1`: prior20 completed-minute range; preceding5-minute
range / preceding20-minute range <=0.65 (existing frozen research contraction
parameter, an explicit operational accumulation proxy, not a PDF numeric claim).
A completed candle strictly sweeps one boundary and closes back inside the range,
in the direction of its real body. Reject candles sweeping both boundaries.
Trigger at that completed reclaim close. Stop one ES tick beyond the actual wick.
Use existing complete_plan risk/volume/trend/entry/1R+2R checks unchanged, including
RVOL>=1.2, 5/15-minute trend confirmation and maximum2ATR risk. Preserve10-minute
scenario lifetime and5-minute cooldown; no options/price conversions.

Baseline: execute the existing HunterRuntime lifecycle and existing complete_plan
with current rolling20 features, including two buffered confirmation closes,
expiry, invalidation and cooldown. Cached rolling features must match direct
production calls; cosmetic SHADOW annotation/file I/O are skipped in replay only.
Replay the entire source chronologically, including outside RTH; invalid/gapped
windows cancel scenarios. Both models receive exactly the same completed bars.

Data: retained artifacts/issue16/data/es_1m.csv.gz (Yahoo continuous ES proxy,
2026-09-21 through2026-10-18). No download, inferred tick tape or SPX options.
Use existing RTH chronological partitions:10train/5validation/5historical-test
sessions,10-minute embargo on both edges. This dataset/test was used in earlier
research, so it is NOT a new pristine external holdout for this project. Record
raw compressed-file hash and exact partitions; never claim proxy/zero-latency
replay demonstrates live performance or SPX-option returns.

Metrics: existing independent movement-event labels and matching (10-minute
horizon, max0.06%/2priorATR target, onset25% of target), precision/recall, early
precision/recall/F1, false alarms/session, misses, median lead and confidence
intervals. Report SETUP/TRIGGER/complete-plan attrition and baseline latency.
Generate decisions before future-outcome censoring; missing outcomes remain
censored, not successful. Reuse existing scorer and event definition unchanged.
Stress availability with1minute extra delivery delay in addition to ideal0delay.
No simulated trades/options P&L; fees/spread are therefore not assumed away in
any profitability claim (none is made).

Necessary improvement gate, fixed now: on validation AND historical-test, new
early-eventF1 must be strictly greater, event precision must not decrease,
false alarms/session must not increase, median matched lead must not worsen,
with >=20scored signals/model and>=5sessions. Must also pass these conditions
under1minute delay. Train is descriptive; no fitting/tuning. Failure means keep
the running detector and notification rules. Passing is necessary but insufficient
for live promotion: independently retained unseen native data and live freshness/
entitlement checks must still support the result; prior historical test is reused.
