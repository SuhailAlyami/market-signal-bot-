# SPX miss attribution: price conditions dominate lifecycle suppression

This is retrospective diagnosis of the already-consumed Oct22 SPX cash sample,
not a new detector, validation set, real-time alert, or trading result. No
production rule, threshold, sender or workflow was changed. Raw data and original
one-to-one scoring remain unchanged. The diagnostic reproduces the baseline
runtime transition list exactly before attributing misses.

## Measured ablation

Suppressing the lifecycle entirely means emitting every original raw price
candidate, including repeats. This is a counterfactual for diagnosis, not a
proposed trading rule. Last ten-minute outcome windows remain censored.

| Stage, zero simulated delivery delay | Scored signals | Matched /16 | Strictly early /16 | Unmatched signals | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original WATCH lifecycle |29|8|1|21|-1minute|
| Every raw price candidate, no lifecycle |84|13|2|71|-1minute|
| Original two-close confirmation |17|4|1|13|-1minute|

Removing cancellation cooldown and repeated-state suppression cannot rescue the
early objective here: it adds55scored signals and one early event, while adding
50unmatched signals. This does not prove cooldown is always good; it establishes
that the candidate information/timing is the larger problem in this fixture.
There are87raw candidates total, including3censored, compared with31WATCH
transitions, including2censored. Of87raw candidates,31start a setup,50occur
while a same-direction scenario is active or on its exit bar, and6are in cooldown.

## Event-by-event attribution

Categories inspect direction-matching raw candidates inside the unchanged
anchor-to-target window. They are explanatory presence counts, not substitute
precision/recall. Strict one-to-one metrics above remain authoritative.

* 11events: first matching price candidate occurs at/after onset.
* 3events: no matching raw price candidate before the target.
* 1event: an early raw candidate exists but the lifecycle suppresses a new setup.
* 1event: an early WATCH exists.

The lifecycle-suppressed case is event2, DOWN: anchor decision14:23UTC
(17:23Saudi), onset14:24UTC (17:24Saudi). Its raw candidate falls inside an
already-active same-direction scenario/exit bar. It is not evidence to alert
on every repeat: the full ablation's71false alarms show that tradeoff.

## Evaluation boundary that must not be hidden

For9/16events, conservative onset is in the minute starting exactly when the
anchor decision becomes available. The strict rule requires detection at/after
the anchor and strictly before onset; those events have no strictly early
decision slot under this labeling convention. This is a measurement limitation,
not permission to backdate detection or credit earlier unrelated candidates.
The other7events leave positive room; the original WATCH is early in just1.

Onset is START of the first minute whose wick reaches25% of the movement target;
minute OHLC cannot reveal intraminute ordering. The event generator also retains
the original close-based eligibility before the conservative wick timestamp is
applied. This diagnostic does not rewrite the event universe or acceptance gates.
Before evaluating a future pre-movement warning, freeze an additional explicitly
defined pre-anchor matching analysis on development data, then validate it on
untouched sessions. Keep the original strict result alongside it. Changing the
metric on this sample cannot establish improvement.

The first30opening bars are warm-up. These results cover only240completed bars
through13:29NewYork on Oct22; they do not assess the later screenshot or the
whole session. No extra early opening success is inferred.

## Delay sensitivity

| Stage | Early events, 0min | Early events, +1min | Early events, +2min |
| --- | ---: | ---: | ---: |
| WATCH |1|1|0|
| Raw candidates without lifecycle |2|1|0|
| Confirmation |1|0|0|

These are simulated fixed delivery delays, not measured provider latency.
Minute-close confirmation is unsuitable as a claim of advance warning simply
because its directional label eventually agrees. More markers are not success.

## Reproduction and verification

```
python diagnose_spx_misses.py --input artifacts/spx_only_development/raw.json --output diagnosis.json --protocol-commit e34df76031a58e2b4b1c54af356ce727f3fe6bcc
python -m unittest discover -s tests -p 'test_spx_miss_diagnosis.py' -v
```

The regression verifies unchanged raw checksum, baseline counts and transition
list, complete attribution accounting, and every claimed early raw candidate's
strict anchor/onset/target ordering. JSON includes all16events and210decision
rows, including non-signals; outcomes are not selected from winning screenshots.
Holdout=false, notifications=false, NOT_READY. No subscription is justified by
this negative diagnostic.
