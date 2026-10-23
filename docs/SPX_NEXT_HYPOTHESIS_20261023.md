# Next SPX research decision: observation required before another hypothesis

Protocol-only checkpoint, 2026-10-23. Product remains NOT_READY; runner action is
WAIT_DATA. No new detector is nominated. No raw market file, new outcome,
Gateway endpoint, account, or credential was inspected in this cycle.

## Evidence reviewed

- SPX_UNSEEN_JULAUG_RESULT_20261023.md: the frozen pullback-release validation
  failed all five gates. Its consumed training diagnostic records 67 matches:
  7 early, 9 at onset, 51 late, with 160 unmatched signals.
- artifacts/spx_unseen_julaug_20261023/training_timing_diagnostic.json:
  172/313 training events have no completed-minute slot between anchor decision
  and conservative wick onset. This does not rule out pre-anchor information.
- SPX_PREPARATION_PROTOCOL_20261023.md and its result: readiness before the EMA
  recross produced only 2 early matches among 70 validation events, 16.67%
  directional precision, median lead -2 minutes, and 10 false alarms/session.
  Recross was also unacceptable. Reduced alert count did not establish an edge.
- SPX_PREMOVE_PROTOCOL.md, SPX_UNTOUCHED_COHORT_20261023.md,
  SPX_HISTORY_COLLECTION.md and SPX_TIMESTAMP_RETENTION.md supply the unchanged
  matching, coverage and timestamp limitations.

These observations do not justify another EMA, compression, pressure, slope,
consensus or threshold variant. They also do not establish a causal mechanism
for a different price pattern. Proposing one solely to consume a new holdout
would spend independent evidence without an evidence-based rationale.

## Exact missing observation

Before proposing a structurally different detector, obtain ONE previously
uninspected complete NYSE session of native SPX cash minute OHLC plus an aligned,
prospectively recorded availability trace from the existing read-only source.
For each completed minute the trace must establish the first local receipt at
which that completed bar was available, with UTC timestamps, provider bar start
and completion semantics, source/instrument identity, and contemporaneous
REALTIME/FROZEN/DELAYED/UNKNOWN classification. Preserve separately any provider
index timestamp and its own receipt time. Do not invent a trade timestamp or
pair asynchronous price/time callbacks as a verified tick-by-tick trade stream.
Unknown or missing availability remains unknown, never zero latency.

A historical request receipt is not the original live availability of each bar.
The earlier isolated type-1 timestamp observation proves neither session-long
coverage nor latency for historical bars. No full-session availability trace is
established by the reviewed checkpoints; this is not a claim that the existing
reader cannot produce one. If its existing output lacks these fields, record
that limitation; do not modify production to satisfy this checkpoint.

The observation is needed to distinguish completed-bar timing constraints from
actual delivery delay. Minute OHLC alone cannot locate an intraminute first
wick; keep the existing conservative onset and label that uncertainty explicitly.
No new directional hypothesis, label, performance result or calibrated confidence
is inferred from this requirement.

## Acquisition boundary and local command

Do not recollect July20-Aug14 or October20-22. Do not inspect Aug17 onward in
this cycle. All July20-Aug14 sessions are consumed development, and existing
September/October inspected sessions cannot become independent evidence.

For the next complete session, retain the existing reader's native SPX evidence
privately without restarting/reconfiguring it, connecting to accounts, or sending
alerts. First eligible date is October23 if its entire trace was already retained;
otherwise use the next full session with prospective coverage. After its actual
NYSE close, obtain its completed historical bars once in a fresh directory. For
October23 ONLY, if not already collected, the documented collector command is:

```powershell
python collect_spx_sessions.py --end 2026-10-23 --sessions 1 --output .hunter-state/spx-availability-20261023/capture --port 4001
```

This command supplies historical coverage only; it does NOT create the missing
prospective trace. For a later date use that actual completed date and a fresh
corresponding directory. Never run the default research/evaluation wrapper.
Port4001 is documented project configuration, not a probed or guessed endpoint.
One daily request, existing timeout/pacing, no retries or alternate source. Full
coverage must follow NYSE holidays, DST and early closes; no filled minutes.
Partial captures remain partial and cannot satisfy this input requirement.

No Gateway recovery is requested: the latest checkpoint documents recovery and
actual type-1 provider timestamps. Missing full-session evidence is not evidence
of a closed Gateway, missing entitlement or required sign-in.

## Frozen plan for the observation, not a candidate evaluation

Once the changed raw input and trace exist, reserve that session as availability
DIAGNOSTIC DEVELOPMENT before opening outcomes. It cannot later serve as untouched
validation/holdout. Check metadata, coverage, completion and receipt ordering first;
report missing pairs and unknown modes. Measure bar-availability lag distributions
and censoring against the existing conservative minute onset. Do not infer exact
intraminute lead. Preserve all failures and raw provider timestamps privately;
publish only sanitized derived coverage/latency artifacts.

No parameter search, directional feature selection, event matching or fresh
performance evaluation is authorized by this protocol. Next hypothesis requires
its own written causal rationale, fixed rules and fresh chronological training,
validation and conditional holdout dates before outcomes. Aug17-Aug20 remains
unacquired/uninspected, with no new role assigned here. Never reuse this
availability diagnostic as independent signal-quality evidence.

For any later candidate, retain the existing event universe and strict one-to-one
anchor/onset matching, ten-minute horizon and causal cooldown. Report precision,
strict early precision/recall, misses, lead, false alarms/session, Wilson/session
uncertainty and 0/1/2-minute latency sensitivity. Keep the five gates unchanged:
precision >=50%, Wilson95 lower >=40%, strict early recall >=20%, median lead
>=1 minute, false alarms <=2/session; no-signal is not acceptance. Require
untouched holdout early-F1 improvement over the original baseline. Passing any
synthetic test is not market evidence. Causality/prefix/future-poison tests are
required before a future implementation is evaluated.

## Cycle checkpoint

Completed only this written evidence/missing-observation decision and RESUME
checkpoint. No acquisition, new outcomes, tests, model implementation, Git writes,
production/auth/workflow/task edits, deployment, notifications or trades occurred.
Tests intentionally not run: the latest scoped RESUME instruction explicitly
requires a protocol-only cycle with no repeated tests. UTF-8/document integrity
checks are permitted and are not market validation. Host runner must review and
save the exact manifest; no commit/push success is claimed here.

Owner action: ????? ????? SPX ???? ????? ????? ?? ????? ????? ?????? ???? ???????
?? ?????? ???????? ?? ???? ?????? ??? ??????? ?????? ????? ??? ????? ??? ???? ??????.
?????? ????????? ????? ?? ???? ?????? ????. ?? ???? ????? ???? Gateway ?? ????? ??????.
