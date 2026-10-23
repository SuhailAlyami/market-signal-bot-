# Native onset forecasting continuation — 2026-10-23: NOT_READY

Starting from the documented coverage/late-confirmation failures, this compares
one genuinely anticipatory WATCH forecast rather than another post-breakout
confirmation. Inputs end at a completed minute; positive training labels require
onset one to three minutes later. Entry rules and operating senders are separate.

The fixed experiment was committed BEFORE performance measurement:
`b6cd10dd6fb18c9df689c7e679524eae495cdb0a`.
Only Sep1–4 fit the eight-feature linear model; Sep8–15 is chronological
DEVELOPMENT validation, six sessions, not an independent test. Source and fine
movement labels are unchanged. Training support:1290NONE/34UP/36DOWN rows.
Four correctness tests cover future-independent features, genuine lead in labels,
training-only normalization, and a WATCH emitted without any breakout/entry.

| Six later development sessions | Signals | Early events | Precision | False/session | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fixed linear forecast | 0 | 0 | undefined | 0 | undefined |
| Existing SETUP with rejection release | 29 | 3/137 | 31.03% | 3.33 | -1.5m |

No-signal behavior is not success. All unchanged absolute gates fail. The paired
earlyF1 interval is[-0.08235,0]. No independent data was acquired or deployed.

## Diagnosis and bounded next step, not arbitrary threshold lowering

The balanced-class softmax outputs are uncalibrated scores. Highest directional
score is0.4627 in training and0.5922 in later development, so the frozen0.65
threshold cannot emit. A score is not a promised win probability. Post-run
ranking diagnostics show some discrimination (later UP one-v-restAUC0.562,
DOWN0.755) but do NOT establish actionable event precision or option returns.

Before testing a policy amendment, commit
`6bcdb9326938c277c3fa92867b2a42c34768d9ce` fixes a bounded TRAIN-ONLY process.
It truncates raw data before September5 before calculating features. Forward
folds fitSep1–2/evaluateSep3 and fitSep1–3/evaluateSep4. Nine policies reuse only
existing L2[.01,.1,1] and threshold[.35,.5,.65] values. Selection requires>=3OOF
signals,precision>=50%,medianlead>=1minute,false<=2/session. Those are preliminary
selection rules; all original full development and independent acceptance gates
remain. Neither later-six-session rows nor July are used to select a policy.

NONE of the nine policies qualifies. Among policies that emit, event precision
ranges6.98–14.53% and false alarms6–89/session. The highest-precision configuration
still has50false/session; the six-false/session configuration matches only1/13
movements and is six minutes late. These are diagnostics of rejected candidates,
not a selected strategy. No later-six-session rerun/refit or independent requests
were spent to rescue this family. Full per-policy metrics are retained in
artifacts/onset_train_policy/selection.json.

This narrows the failure: the fixed threshold alone explains the initial silence,
but a principled training-only policy search still fails event quality. Changing
alert names, lowering thresholds or declaring rankAUC as a trading edge would
not solve the task. It does not prove every OHLCV model impossible or that richer
data guarantees success. The untouched twenty-session July sample stays reserved.
No new predictive Python/Pine rollout is justified by these results.

Production strategy, Gateway settings, subscription permissions and Telegram
verification were not changed by this research. The definite lifecycle repair
from PR40 remains distinct from predictive readiness. See local RESUME.md for
the newly observed operational reader stoppage and recovery, kept separate from
these research metrics. No trades or paid services.
