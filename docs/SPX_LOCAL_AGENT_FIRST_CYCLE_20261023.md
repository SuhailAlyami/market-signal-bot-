# Actual first Windows SPX cycle and recovery - 2026-10-23

The scheduled Codex call ran once. It reached documented TCP4001 and passed four
synthetic collector tests, then correctly reported BLOCKED when the model's
workspace-write sandbox denied linked Git index.lock access. It did not claim
market-data or detection success. The host reviewed and pushed the exact three
checkpoint files in4bdb98ef947ec25ee7c18e4788ea9654ca37b2f4, preserving private logs.

The host then executed the already committed acquisition plan once:
`python collect_spx_sessions.py --end 2026-10-19 --sessions 1 --output .hunter-state/spx-gateway-check-20261023-oct19/capture --port 4001`
Actual IBKR SPX/IND/CBOE historical session returned390/390 expected NYSE minutes,
complete=True. Contract identity, raw hash, receipt and coverage appear in the
sanitized result artifact; raw provider files stay private. No accounts,
positions, orders, credentials, options or subscriptions were requested.

This proves that historical API request, not REALTIME/FROZEN/DELAYED quote mode,
latency or detection quality. No detector outcomes were scored. One session is
not independent12/4/4 chronological evidence, and October23 is not complete
until20:00UTC. Quality remains NOT_READY. This session is acquisition-only,
uninspected for strategy outcomes; it is not renamed as independent validation.

Operational fixes retain the model sandbox and budgets. The host runner validates
an exact at-most20file research manifest before committing; production/instruction
changes, unlisted files, private/raw files, traversal, links, renames and deletes
are rejected. Daily YYYY-MM-DD.raw.json inputs now wake WAIT_DATA as well as
raw.json; derived reports do not. Eleven focused worker/guard tests passed.

Current worker state is recovered WAIT_DATA: need genuinely new complete SPX
sessions for the frozen forward protocols. No new model call was used for host
recovery, no quota/backoff was reset. The task remains registered and waiting;
not every15minute tick spends an inference. The daily collector is NOT silently
scheduled during WAIT_DATA. A separate bounded collection after a complete NYSE
session must provide a new raw input. No experiment is deployed or alerted.
