# Shared handoff log (Claude = implementation, ChatGPT/Codex = review)

GitHub is the source of truth. Update this file after each completed phase and before long operations.
Self-review is not independent review. One agent per file set at a time.

## Current state — 2026-11-10 03:45 UTC (owner of next step: Claude; review requested from Codex)

**Status:** NOT_READY / RESEARCH_ONLY. Alerts OFF. No orders.

**Running experiment (the only one):** frozen constituent-breadth forward test.
- Rule: `research/breadth_20261109/protocol.json` (fc4f002). Forward protocol: `research/breadth_20261109/forward_protocol.json` (on main since #56, 418d121).
- Development result (consumed dates, not validation): rejected as a trading rule; C1 passed, C2/C4 failed; audit: no implementation defect, weak statistics (block bootstrap includes 0; Bonferroni bound p = 0.48 over 36 protocols).
- Forward acceptance: C1-C5 all required (incl. C2 net at cost 1 > 0). Single look at >= 190 high-agreement events (conditional estimate; ~757 if the true effect is half).
- Outcome-free count 2026-11-10 03:40 UTC (`run.py --forward`, no outcomes computed): 3 synchronized forward sessions (2026-11-05, 11-06, 11-09), 7 high-agreement events, 183 to go (~2.1 per session).

**Data collection:** `.github/workflows/spx_collect.yml` on main writes `data/spx-collection` (SPX 1m + 5m for ^GSPC and 10 stocks).
- Manual runs green: 42697651406 (60d backfill), 42735200261 (stored 2026-11-09, 11/11 symbols, 60 synchronized sessions).
- BLOCKER: no `event=schedule` run of spx-collect has ever occurred. The 2026-11-09 21:45 UTC slot had not fired 6 h later; `frozen_day_research` (cron 21:35 UTC) also has no schedule run since 2026-11-07 01:07 UTC (historically 3.5-5.5 h late). Cause unknown (GitHub-side delay/drop suspected; workflow state active).
- Proposed fix (this branch, not merged): one backup cron `7 1 * * 2-6` (04:07 Riyadh). Collector dedupes identical payloads; first read stays canonical.

**Decision on new experiments:** none started. Reasons: 36+ preregistered protocols already used the same consumed data (multiplicity); the decisive evidence for the only surviving candidate must come from forward data; the binding blocker is unproven automatic collection. Starting another development test would add cost without independent evidence.

## Branches / PRs
| Item | State |
|---|---|
| main 418d121 | collector + frozen breadth forward test (PRs #55, #56 merged) |
| PR #54 `claude/kind-ramanujan-icu95e` (ce33722) | research record + RESUME.md; draft, do not merge |
| `feat/collector-resilient-fetch-20261110` (e150efb) | paused by owner (retry/backoff + format checks); no PR |
| `coord/handoff-schedule-20261110` | this log + backup cron; draft PR |

## Review needed (Codex)
1. Backup cron change: confirm it cannot double-write or race (single concurrency group, fast-forward push, payload dedupe).
2. Independently re-check `research/breadth_20261109/test_forward.py` equivalence claim (dev output byte-identical) and that `run.py --forward` computes no outcomes below 190 events.

## Resume command
1. Read this file and RESUME.md on PR #54; `git fetch origin` and check open PRs / latest commits for concurrent work.
2. Check spx-collect runs for `event=schedule`. If none after the backup cron is merged and two slots pass, record it here and escalate to the owner (GitHub-side).
3. Only for counting: `python research/breadth_20261109/run.py --forward <data/spx-collection:breadth5m/bars5m.json>`. Do not score before 190 high-agreement events. Do not tune anything.
