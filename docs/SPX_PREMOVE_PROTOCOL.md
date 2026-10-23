# SPX pre-movement experiment v1, frozen before new history acquisition

Native SPX IND minute OHLC only; no volume, ES/NQ, options, delivery or orders.
This protocol proposes unvalidated hypotheses. It does not assert predictability.
Preserve provider arrays and exclude incomplete bars using min(receipt,chart_end).
Obtain ONE_MONTH/ONE_MIN history once through the existing read-only IBKR connector.
Do not increase costs or change production. No acquisition retry if the history
request merely exposes too little history; report the coverage limitation.

Exclude Oct22 2026 (consumed development) and later dates from new quality splits.
Only native NYSE full regular sessions with every expected minute valid count.
Never fill a missing minute or fabricate volume. Require at least20full sessions;
chronological split floor(60%)/floor(20%)/remainder, minimum12/4/4sessions.
All features and signals are computed causally within each session. Last10minutes
have unobservable outcomes and are censored without changing signal scheduling.
Whole-session splits avoid overlapping ten-minute horizons across partitions.

Prior20 ATR uses true ranges excluding the current bar. Features need31contiguous
completed minutes. Five-bar compression means prior5 high-low divided by prior20
high-low. Current close position means (close-low)/(high-low). EMA5/EMA15 are
session-local, evaluated at the completed current bar.

Fixed candidate set, no further parameter search after results:

1. Compression pressure: prior5/prior20 span <= q for q in{0.35,0.50,0.65};
   UP if current close>open, close>close3ago, close position>=0.65;
   DOWN symmetric with close position<=0.35. A break of20bars is NOT required.
2. Trend pullback release: EMA5>EMA15 and close15ago<close, previous close<=
   previous EMA5, current close>EMA5 and bullish body; DOWN symmetric.
3. Sweep/reclaim baseline: prior20 extremum swept and reclaimed with matching
   body, excluding a two-sided sweep. No direct-break fallback.
4. Original spx-price-watch-v1 candidate without lifecycle and no-signal baselines.

Every candidate schedule has a fixed10-minute same-model cooldown; no future
label may determine which candidate consumes cooldown. Do not introduce the old
scenario/confirmation lifecycle into these early-warning hypotheses.

Retain the existing independent movement universe: nonoverlapping10minute
targets max(0.06% close,2priorATR); same-bar two-sided targets excluded.
Keep original strict anchor-to-target one-to-one scoring, and report the
conservative start-of-first-wick-minute25%-target onset used in SPX replay.
Additionally report, separately, a fixed pre-anchor matching diagnostic: signal
may be up to3minutes before an anchor, must strictly precede onset, target must
occur within10minutes of actual decision, one signal/event, chronological greedy
matching. This auxiliary metric must NEVER replace strict acceptance gates.

Choose one non-baseline configuration on training strict EARLY F1, ties by fewer
false alarms then fixed model ID. Validate exactly that model once. Holdout is
opened only if validation meets the unchanged quality gates: precision>=50%,
Wilson95% lower precision>=40%, early event recall>=20%, median lead>=1minute,
false alarms<=2per full session. Report no-signal and original baselines on the
same splits, Wilson intervals, misses and0/1/2minute simulated delivery delay.
If validation fails do not inspect holdout outcomes or tune on validation.
Report NOT_READY and preserve negative results. Insufficient20-session coverage
also means NOT_READY with no claim of independent validation.

If coverage is insufficient, the already-consumed Oct22 fixture may be used only
for a clearly marked development smoke and debugging, with all settings above
unchanged. It cannot qualify a model or justify deployment. A passed CI run or
a single favorable screenshot does not change the decision.
