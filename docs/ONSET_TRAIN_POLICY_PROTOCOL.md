# Train-only policy selection amendment, before measuring candidate performance

The first registered L2=1/threshold0.65 model emitted no validation warning.
Post-run diagnostics show its directional scores never exceed0.463 in training
or0.593 in consumed validation. These are uncalibrated balanced-class scores;
0.65 does not mean65%probability. Ranking AUC differs by direction and does NOT
prove an actionable edge. No direct tuning against those validation rows.

One bounded selection procedure uses ONLY the first-four training sessions.
Existing research constants are reused: L2 in[0.01,0.1,1],threshold in[0.35,0.5,
0.65],margin0.1, hysteresis gap0.15 (the original0.65minus0.5).
Forward folds: fitSep1–2,scoreSep3; fitSep1–3,scoreSep4. Same native features,
labels, min10directional training cases, causal state and event scorer. No
random split. Fold support failure is reported, never relaxed.

Aggregate out-of-fold signals/events chronologically acrossSep3–4. A policy
is admissible for further DEVELOPMENT validation only if it has>=3signals,
movementprecision>=0.5,medianlead>=1minute,false<=2/session. These selection
support rules are NOT independent acceptance or a relaxed live promotion gate.
Among admissible policies choose maximum earlyF1, then fewer false alarms,
then stronger regularization, then higher threshold. If none qualifies, stop
this candidate family and do not rerun the six later sessions just to search.

If a policy qualifies, fit its selected L2 once on all first-four sessions,
serialize its fixed policy/model and commit BEFORE the six-session validation
run. The same complete absolute/paired/stress gates still apply to that later
development comparison and untouched July still remains required for adoption.
Existing fixed-model results remain recorded. No threshold selected from the
six later sessions, independent source, live stream or option outcomes.
