# Half-minute timing diagnostic — not the frozen quality study

Native SPX IND/CBOE1000bars/30seconds acquired. Metadata only inspected so far:
Oct21 18:10UTC to Oct22 19:59:30UTC. Oct22 minute prices are already consumed;
new intraminute details do not make this independent validation.

Before computing outcomes, fix this separate experiment. Do not alter v1/v2
production or the frozen20-session protocol, or reuse this metric for acceptance.

Integrity: preserve arrays, validate native identity, positive finite valid OHLC,
unique ordered aware30-second starts and completion via min(receipt,chart_end).
Aggregate minutes ONLY from both native half-bars (open first, max high, min low,
close second), no filling. Require a complete Oct22 NYSE session of780half-bars.
Cross-check all390aggregated minutes against the prior1000minute capture;
stop the paired comparison if any OHLC differs. Ignore partial Oct21 performance.

Models: exactly `pullback_release`, `compression_0.35`, `prelevel_pressure` with
unchanged thresholds/formulas from their existing source. Two decision clocks:

- Minute close: current completed minute, existing features/rules.
- Midpoint: current minute's FIRST native half-bar only, plus completed previous
  minutes. Need31previous valid completed contiguous minutes; current partial
  minute must be valid. Prior20ATR/levels/compression use completed past minutes.
  EMA5/15 provisional current values are alpha*half-close+(1-alpha)*previous
  completed-minute EMA. move3/15 compare half-close with completed close3/15
  minutes ago. body/position use the native first half OHLC. OLS5 for prelevel
  uses previous4completed closes plus half-close. Never read current second half
  or current full close for midpoint features. No synthetic live-feed claim.

Keep causal ten-minute cooldown separately for each model/clock BEFORE future
outcome censoring. Minute-close decisions use their existing31bar warmup from
index30; midpoint starts with31previous completed minutes from index31. A
minute-close signal at index30 may consume cooldown even before scored label
eligibility; do not schedule using future labels.

Common higher-resolution outcome universe for BOTH clocks, fixed now:
native30second OHLC; eligible anchor after31previous valid completed minutes,
current native half close known at anchor-start+30seconds. Its target is
max(0.06%anchor-close,2*prior20MINUTE ATR). ATR is known before the anchor half
starts, from the preceding20completed minutes (true ranges with prior close).
Seek first directional target over next20native half-bars (10minutes), exclude
ambiguous same-half two-sided target and retain existing close-touch25%-target
eligibility. Greedy nonoverlap advances21half-bars after an accepted anchor.
Onset is START of first future native half-bar touching25%target in that direction;
intrahalf ordering remains unknown. Event labels are fixed independently of models.

Map midpoint signals to the first half-bar index, minute-close signals to the
second. Each closes30seconds later. Existing strict one-to-one anchor-index to
target-index scoring uses horizon20half-bars, delivery<=target HALF-BAR START,
and conservative onset above. Thus neither clock can match an anchor whose close
was unavailable at its own decision. Report0/30/60/120second simulated delivery
delay. This native-half event universe is DIFFERENT from v1 minute labels and is
diagnostic only; never compare its hit counts directly with the old16/12events.

Preserve all six model/clock rows, every scored signal/match, misses, early
precision/recall, Wilson intervals, median lead, censoring and input hashes.
Test midpoint invariance to changing the future second half and later prices.
Report negative outcomes; no tuning, selected winner, deployment or real orders.
Status remains NOT_READY regardless of point estimates on this consumed session.
