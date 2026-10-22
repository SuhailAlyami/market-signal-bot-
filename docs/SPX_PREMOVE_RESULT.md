# Frozen pre-movement price hypotheses: no deployable success

Protocol commit355c2d8d728b119c4768c6767051132fe7afd8d6 was published before
requesting new SPX history. Exact native US SPX IND resolved again to416904,
CBOE. Two read-only ONE_MONTH/ONE_MIN requests were rejected by the IBKR
connector. No provider error text, credentials or authentication URL is persisted.
No substitute symbol, fabricated prices or synthetic index volume was used.
After the development pass, a final read-only acquisition alternative using an
explicit10000bar count instead of period was also rejected. This was an access
format alternative, not a model/threshold change; no new usable data arrived.

The minimum20complete independent sessions needed for12/4/4(or larger) temporal
train/validation/holdout partitions are unavailable in this run. Those quality
partitions were NOT executed. No configuration was selected and no holdout was
opened. The code below is a consumed-sample development implementation/smoke,
not a completed walk-forward evaluation engine or an out-of-sample result.

The already-consumed Oct22 fixture has240completed native SPX bars and16movement
labels. All frozen configurations were applied without subsequent threshold
changes. Every model has a causal10-minute cooldown, including the original
candidate baseline, so this baseline is distinct from the prior state-machine
WATCH's29scored signals. Invalid history/first30bars remain excluded. Last ten
minutes are censored from outcomes but still consume candidate cooldown.

| Fixed hypothesis | Scored signals | Matched /16 | Strict early /16 | Unmatched | Median lead | Auxiliary pre-anchor early /16 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Compression<=0.35, directional pressure |12|4|1|8|-1.5min|1|
| Compression<=0.50, directional pressure |16|3|0|13|-2min|1|
| Compression<=0.65, directional pressure |18|3|0|15|-1min|2|
| EMA pullback release |10|0|0|10|n/a|4|
| Sweep/reclaim only |5|1|1|4|2min|2|
| Original raw candidate,10min cooldown |17|2|0|15|-2min|3|
| No signal |0|0|0|0|n/a|0|

The last column uses the newly frozen auxiliary allowance of up to3minutes before
the anchor, strictly before onset, with target no more than10minutes after actual
delivery. It is NOT substituted for strict acceptance. For example, crediting4
early pullback events under this different diagnostic cannot turn its0strict
matches into a proven improvement. There is no selected winner here.

The apparently better sweep median lead is from only ONE strict match out of
FIVE signals. Its observed precision20% does not meet the50% gate, and a one-match
median is unstable. None of the non-baseline fixed models meets the unchanged
quality gates even on this consumed fixture. An extra subscription is not
justified by these results.

JSON retains Wilson95% intervals and0/1/2minute delay sensitivities for every
model, all signals, censoring counts and negative results. Onset retains the
conservative first-wick-minute-start semantics;9/16events have no strictly early
anchor-to-onset decision slot. This limitation is unchanged and disclosed in
SPX_MISS_ATTRIBUTION.md. No event definition was retuned after seeing outcomes.

Reproduce:

```
python research_spx_premove.py --input artifacts/spx_only_development/raw.json --output premove.json --protocol-commit 355c2d8d728b119c4768c6767051132fe7afd8d6
python -m unittest discover -s tests -p 'test_spx_premove.py' -v
```

The future-perturbation regression verifies identical decisions for every model
before a changed future suffix, and the auxiliary matcher is tested against late
delivery and an out-of-horizon target. Production detector, lifecycle, sender,
workflow, secrets and old Pine are unchanged. Readiness remains NOT_READY;
notifications and orders stay off. The remaining evidence requirement is native
SPX minute history covering at least20full independent sessions through the
authorized source, followed by the frozen chronological procedure. Neither
monthly request rejection nor a passed CI test proves detection is impossible.
