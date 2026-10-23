# One bounded local SPX research cycle

Read AGENTS.md, RESUME.md and the latest protocols/results first. You are running
in the owner's separate `research/local-spx-agent` worktree. Complete ONE small
research/engineering step within 12 minutes, leaving time for tests and checkpoint.
SPX cash only. Continue from measured evidence; do not restart prior experiments.

Mission: improve early detection with falsifiable causal hypotheses and independent
chronological data, preserving failures as well as successes. Current NOT_READY is
the honest starting point. A passing test or single successful alert is not an edge.

Current next step: check read-only local Gateway access and the existing daily
collector. Do not guess its port: inspect non-secret project configuration or test
documented loopback endpoints for connectivity only. Never access accounts,
positions, orders, credentials or secret files. Preserve provider timestamps and
raw SPX data. Collect only complete sessions; distinguish receipt/decision/trade
times, REALTIME/FROZEN/DELAYED and NYSE hours/holidays/DST. No alternate price source.
If there is no usable new data, report WAIT_DATA with exact required input and
document a local collection command. Do not repeatedly retune Oct20–22 samples.

For new logic: commit a written hypothesis, event definition, frozen parameters,
data split, acceptance gates and evaluation plan BEFORE inspecting its outcomes.
Use training-only selection, untouched validation/holdout, event precision/recall,
strict lead time, false alerts/session, misses and latency sensitivity. Do not
change gates to declare victory. Never reuse consumed holdout as independent.
Test causality/prefix/future-poison where relevant. If independent evidence is
insufficient, preserve NOT_READY. If a gate passes, report CANDIDATE_FOR_REVIEW;
do NOT auto-enable alerts, deploy or describe profits as established.

No edits to production detectors, workflow files, auth, account settings, AGENTS.md,
this worker or its instructions. Put experimental variants in new research files.
No new subscriptions, paid API keys, limitless loops, trading, Telegram, pushes to
main, force pushes, merges, deletion of results, or PR spam. Keep the existing PR
as context; new local work remains on this separate research branch.

Before exit: run appropriate tests, save results and a concise Arabic checkpoint
in RESUME.md with dates, hashes, commands, measured negatives and next step. Commit
only explicit research files (never `git add .`, logs, auth, .hunter-state or raw
private gateway dumps). Push this branch normally if network permits. If unable
to commit safely, stop with BLOCKED and preserve files for recovery. Do not claim
GitHub saved until push succeeds. Runner retries a pending push before new work.

Return JSON status CONTINUE only with a concrete useful next step that does not
require missing data. WAIT_DATA or NOT_READY waits for a changed raw.json input;
BLOCKED pauses for local recovery; CANDIDATE_FOR_REVIEW pauses for review.
The runner's two-calls/day ceiling is an invocation limit, not a token/cost guarantee.
