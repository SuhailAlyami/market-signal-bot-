# Isolated local agent assignment

Prepared for Antigravity; this file does NOT claim the agent has run.
Implementation base: `c4ca1e75d6afdfab0cf4ca168a3a216d0bafcad2`. Work only in this worktree and its current branch.
Read AGENTS.md, the relevant RESUME.md entries and docs/SPX_MULTI_AGENT_HANDOFF.md.

Audit SPX cash data identity, provider/receipt/decision timestamps, complete candles, gaps, DST/calendar, future leakage and holdout independence. Distinguish confirmed bugs from suspicions. For each confirmed bug give file/function, minimal reproducer and a failing targeted test. Do not modify the production detector or run market acquisition.

Write `docs/AGENT_DATA_AUDIT.md`. Return the exact commit SHA and evidence, not just a summary.
Do not access secrets/account logs, change production, send alerts, place orders, purchase services, reset quotas, or weaken sandbox permissions. Reuse only an already authenticated available model. Keep independent data genuinely independent. Quality remains NOT_READY without new evidence.
Git metadata is outside this linked worktree: if sandbox prevents committing, leave an exact changed-file manifest for the host; do not alter ACLs or permissions. Do not edit another agent worktree.
