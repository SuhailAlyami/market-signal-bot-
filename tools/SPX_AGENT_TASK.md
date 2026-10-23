# One bounded local SPX research cycle

Read AGENTS.md, RESUME.md and the latest protocols/results first. You are running
in the owner's separate `research/local-spx-agent` worktree. Complete ONE small
research/engineering step within 12 minutes, leaving time for tests and checkpoint.
SPX cash only. Continue from measured evidence; do not restart prior experiments.

Mission: improve early detection with falsifiable causal hypotheses and independent
chronological data, preserving failures as well as successes. Current NOT_READY is
the honest starting point. A passing test or single successful alert is not an edge.

Initial step ONLY if no measured local acquisition checkpoint exists: check
read-only local Gateway access and the existing daily collector. Once RESUME.md
records actual provider acquisition, continue from that evidence; do not repeat
its connection/tests or collect the same completed capture again. Do not guess its port: inspect non-secret project configuration or test
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

Before exit: run appropriate tests and save a concise checkpoint in RESUME.md.
Write UTF-8 bytes; avoid legacy PowerShell pipes/redirection for Arabic text.
Windows workspace-write deliberately protects linked Git metadata: do NOT try
Git writes, change permissions or bypass the sandbox. Return checkpoint_files:
EXACT relative paths of all changed research files, at most20. The trusted runner
validates this manifest and commits/pushes outside the model sandbox. Allowed:
RESUME.md; NEW docs/*.md, derived artifacts/*.json/*.csv/*.md (never raw.json),
NEW root research_spx_*.py and NEW tests/test_spx_*.py. No deletes, renames,
production/instruction/auth changes or private logs/dumps. If no changes, return
an empty list. Do not claim GitHub saved before the runner records push success.

Return JSON status CONTINUE only with a concrete useful next step that does not
require missing data. WAIT_DATA or NOT_READY waits for a changed raw.json input;
BLOCKED pauses for local recovery; CANDIDATE_FOR_REVIEW pauses for review.
The runner's two-calls/day ceiling is an invocation limit, not a token/cost guarantee.

Return needs_gateway=true ONLY if you have evidence that further progress needs
the owner to open/sign in to IB Gateway or approve its local read-only connection.
Do not infer this from closed NYSE hours, a FROZEN close, insufficient completed
sessions, or NOT_READY market results alone. Otherwise return false. In summary
and next_step state the exact missing input and the owner's concrete action in
Arabic, without secrets or raw authentication/provider errors. The runner emits
a deduplicated local desktop notice, separate from market/Telegram alerts.
