# Execute the frozen SPX study after acquiring native daily bars

`evaluate_spx_sessions.py` implements the chronological train/validation/holdout
experiment frozen in `docs/SPX_PREMOVE_PROTOCOL.md`, commit
`355c2d8d728b119c4768c6767051132fe7afd8d6`. It changes no detector or alert runtime.
The native Gateway collector is documented in `docs/SPX_HISTORY_COLLECTION.md`.

## Commands

On the computer hosting the already configured Gateway, from PR41's branch:

The single-command entry point performs both steps and automatically stops
before research if acquisition fails or any requested minute is missing:

```powershell
python run_spx_research.py
```

It uses the already-configured localhost port4001 and a separate client ID,
requests20sessions ending2026-10-21, and creates a new timestamped directory under
`.hunter-state/` containing `capture/` and `study.json`. Use `--port` only to match
the existing Gateway setting. It does not install dependencies, sign in, change
settings, open options subscriptions, send alerts, or access account/order APIs.
The existing `requirements.txt` and `requirements-gateway.txt` define dependencies.

The two individual commands remain available for inspecting each stage:

```powershell
python collect_spx_sessions.py --end 2026-10-21 --sessions 20 --output .hunter-state/spx-history-20 --port 4001
```

After the capture finishes with exit code 0, run:

```powershell
python evaluate_spx_sessions.py --capture .hunter-state/spx-history-20 --output .hunter-state/spx-study-20.json
```

Use new capture/result paths for each attempt; existing results are not replaced.
Exit code 2 means NOT_READY, including a valid negative research result. Review
the result's reason and gate checks; do not tune on validation or rerun many
configurations against a revealed holdout. A new capture of the same historical
dates does not turn those dates into an independent fresh test.

## Dataset and isolation checks

- Read and SHA256-check each daily raw file against the collector's manifest.
  Hashes bind the report to its inputs; they are not a provider signature.
- Require SPX / IND / CBOE / USD and one resolved positive contract ID throughout.
- Require the exact daily historical request, receipt after session close and
  provider start/end bounds. These bounds remain unchanged as provenance.
- Recompute NYSE expected minutes from raw OHLC using the collector's validation;
  do not trust `.validated.json` or the manifest's completeness claim alone.
- Reject partial captures, missing minutes, conflicting duplicates, mixed
  contracts, unordered dates and all dates on/after consumed Oct22 2026.
- Require at least 20 complete sessions. Split whole sessions 60% / 20% /
  remainder, with minima 12 / 4 / 4. Features restart each session; opening
  warmup and final ten-minute outcome censoring are preserved. Outcome windows
  cannot cross a close or a partition boundary.

Integrity checks read all raw files, including holdout OHLC, solely to check
coverage/validity. Holdout features, events, scoring and outcomes are not computed
until the validation gate passes. This distinction is explicit in the program.

## Frozen model selection and evaluation

The training grid contains exactly the frozen compression thresholds 0.35/0.50/
0.65 and pullback-release hypothesis. Sweep/reclaim, original candidate and
no-signal are fixed baselines, not extra train-selected configurations. Training
selects the highest strict EARLY F1; ties use fewer false alarms then model ID.
All model schedules retain their fixed causal ten-minute cooldown before outcome
censoring. No target outcome determines which signal consumes cooldown.

Validation evaluates only that selected hypothesis and the three baselines.
Holdout is not evaluated if any frozen validation gate fails: precision >=50%,
Wilson95% precision lower bound >=40%, early recall >=20%, median lead >=1min,
false alarms <=2 per complete session. Auxiliary three-minute pre-anchor matches
are reported separately and never decide a gate. No threshold is tuned using
validation results. Strict scoring retains the pre-existing anchor-to-target
matching rule and conservative wick-minute onset definition.

If validation passes, evaluate the selected hypothesis and the same baselines on
holdout once. Research acceptance additionally requires the same quality gates
on holdout and strict EARLY F1 greater than the original candidate baseline.
This extra guard prevents claiming improvement from an inferior holdout result;
it does not weaken any frozen gate. A passing status is
`RESEARCH_GATES_PASSED`, not production readiness. Notifications and orders remain
disabled in every result. Live shadow evidence and actual latency checks are
still required before deployment.

The JSON preserves split dates, input hashes, all training configurations,
validation and conditional holdout metrics, event labels, every scored signal
and its match/miss, censored counts, Wilson intervals, deterministic session
bootstrap intervals and 0/1/2-minute simulated delivery delay. Historical bars
cannot establish actual live arrival latency or executable option performance.

## Holdout reservation and interrupted evaluations

Before computing holdout outcomes, the CLI exclusively creates a reservation for
each holdout session under `.hunter-state/spx-holdout-locks/<protocol-commit>/`.
Keep this registry across runs and run from the same checkout directory. A
different output filename or a new capture receipt cannot reopen a reserved
session. Overlapping holdout dates are also rejected; a formerly held-out date
cannot subsequently enter training/validation under the same protocol. A failed
reservation may conservatively leave preceding session dates reserved.

The output path is reserved before calculations start. A report checkpoint is
written before holdout scoring. If scoring fails, the result records
`holdout_opened=true`, `NOT_READY` and a sanitized failure type; reservations are
preserved. Failed validation creates no holdout reservations. Do not delete the
registry or change `--registry` to make consumed data look independent. This is
a local accidental-reuse guard, not a provider signature or a cross-machine
registry; older/manual evaluations outside this tool are not detected.

## Verification and current evidence

Offline tests verify 12/4/4 chronological isolation, insufficient-data rejection,
training selection using early rather than eventual directional matches,
validation-gated holdout access, fixed baseline evaluation, cross-session label
horizon isolation, raw-hash checks, missing-minute rejection despite a forged
completeness flag and exclusion of consumed dates. Synthetic fixtures test
implementation behavior only; their passing metrics are not market evidence.

The existing consumed Oct22 development result remains negative and NOT_READY.
No independent 20-session native capture is present in this cloud workspace,
so the real chronological study has not run. The user's local Gateway cannot be
reached from here. Neither green CI nor this runner is evidence of an early edge.
