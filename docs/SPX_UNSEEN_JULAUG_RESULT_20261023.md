# Frozen native SPX cohort result - 2026-10-23

Preregistered cohort commitdaff1cf9669e2070324dfedfca2bbbba7aedb409; original protocol355c2d8d728b119c4768c6767051132fe7afd8d6. One native read-only acquisition succeeded:July20-Aug14,20complete sessions,7800/7800minutes. Raw/provider request/receipt/bounds stay private; capture_manifest.json preserves per-day hashes and coverage. Historical capture is separate from live reader evidence.

Training selected pullback_release using the original frozen grid and tie breaks. ValidationAug5-Aug10 failed all five gates; evaluator exit1 represents this valid negative result, not a runtime crash. HoldoutAug11-Aug14 outcomes/features were NOT evaluated.

| Validation metric | Selected pullback_release | Original candidate |
|---|---:|---:|
| Signals |82|124|
| Matched directional precision |25.61percent|39.52percent|
| Strict early events /95 |2|0|
| Strict early precision |2.44percent|0percent|
| Median lead |minus1minute|minus3minutes|
| Unmatched false alarms/session |15.25|18.75|

Selected precision Wilson95percent interval17.40-36.00percent. Earlier timing and fewer ordinary false alarms than the original do NOT satisfy the gates or establish useful detection. Auxiliary pre-anchor recall8/95 is diagnostic only and does not replace acceptance. No current/alternative detector is promoted by default; NOT_READY.

## Consumed-training timing diagnosis

research_spx_timing_diagnostic.py reads only saved TRAINING outputs; no new metrics on validation/holdout. It checked saved match-count consistency. Of67matched pullback-release training signals,7were early,9at onset,51late;160others unmatched. The rule requires an EMA5recross before emitting, consistent with confirmation occurring too late for a readiness alert. This observational attribution is not proof a new rule will work.

172/313training events have no completed-bar slot between the fixed anchor decision and wick onset. That is a limitation of this constrained matching window, not proof there are no earlier signals before the anchor. Event universe and acceptance criteria remain unchanged. Full negative outputs and0/1/2minute stress results are retained in artifacts/spx_unseen_julaug_20261023. No raw bars, account data, secrets, trades or test alerts were published/sent.
