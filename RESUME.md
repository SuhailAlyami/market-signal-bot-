# RESUME.md — Suhail Hunter

**Status: NOT_READY / RESEARCH_ONLY.** Alerts OFF. No real trading. Next-session direction/high/low forecasting is a separate experiment.

Last updated: 2026-11-08 (branch `claude/kind-ramanujan-icu95e`, based on open PR #51 head `446add9`).

## 2026-11-10 03:45 UTC update
Shared Claude/Codex log: `HANDOFF.md` in draft PR #57 (also adds a backup cron 04:07 Riyadh). Still no `event=schedule` run of spx-collect. Outcome-free forward count: 3 sessions, 7/190 high-agreement events. No new experiment started (multiplicity; evidence must come from forward data).

## Resume point (2026-11-09 21:00 UTC) — read this first

- Status NOT_READY / RESEARCH_ONLY; alerts OFF. PR #54 (this branch) stays unmerged. PR #55 and PR #56 are merged into main (418d121).
- Detector decision: price-only wave/reversal family STOPPED (`research/spx_review_20261109`). Only candidate kept: constituent-breadth agreement, REJECTED as a trading rule, FROZEN for one forward test (`research/breadth_20261109`, `forward_protocol.json` on main).
- Collection on main (`.github/workflows/spx_collect.yml`, daily 21:45 UTC = 00:45 Riyadh Tue-Sat): SPX 1m (root of `data/spx-collection`) + 5m bars for ^GSPC and NVDA, MSFT, AAPL, AMZN, GOOGL, META, AVGO, TSLA, BRK-B, JPM (`breadth5m/`).
- Backfill run https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/42697651406 (breadth_range=60d, all steps green) -> data commit 9a0ec60: 11/11 symbols, 59 synchronized sessions 2026-08-17..2026-11-06, no missing (day, symbol), 11 raw snapshots with matching sha256; SPX 1m first reads unchanged. 2026-11-09 was still open at fetch time and excluded as incomplete; the next scheduled 5d run should add it.
- Untouched forward sessions so far: 2026-11-05, 2026-11-06 (synchronized). Forward test NOT run and NOT evaluated.
- Next: let the schedule run. Run `python research/breadth_20261109/run.py --forward <breadth5m/bars5m.json>` only to count events; it scores nothing before 190 high-agreement events (conditional; ~757 if the true effect is half). Acceptance needs C1-C5 all (incl. C2 net at cost 1 > 0, C4 vs random direction, C5 block bootstrap). Passing would still mean NOT_READY until receipt latency is verified.
- 2026-11-10 01:21 UTC: the 21:45 UTC schedule of 2026-11-09 had not fired after 3.5 h (workflow active on main; no schedule run of spx-collect yet). Repo history shows GitHub delays schedules here by 3.5-5.5 h (frozen_day_research cron 21:35 UTC ran at 01:07-03:01 UTC). Manual run https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/42735200261 (green, data acb6bb3): 2026-11-09 complete for 11/11 symbols (78 bars each) and SPX 1m (390); 60 synchronized sessions, none missing. Automatic collection still UNPROVEN until a run with event=schedule appears.
- Watch: a red `spx-collect` run (any missing symbol/day is reported, never filled). Yahoo 5m keeps ~60 days, 1m ~7 trading days.

## Current state (2026-11-08) — read this first

- `main` (`6ff3eb5`, 2026-10-29) is NOT the latest research. Newest work lives in open, unmerged PRs:
  #51 `feat/capitalcom-cfd-research-20261029` (updated 2026-11-07, includes the 2026-11-07 objective review),
  #53 draft `feat/spx-direction-wave-20261104`, #46, #45. This branch stacks on #51.
- Latest detection test: `research/objective_review_20261107/` (wave_capture, ensemble_audit, early_agreement,
  profit_protection). **Reproduced byte-identical on 2026-11-08** (sha256 of all results/summaries match; all their tests pass).
- New experiment this cycle: `research/objective_review_20261107/opening_seed/` — single change (seed ATR6 at the open from
  the prior session's last six 5m true ranges), preregistered in commit `a81bf97` before results.
  Result: **REJECT_CHANGE_KEEP_CONTROL**. Early (<=25%) reference matches 32->48 in the older block but 16->16 in the recent block;
  unmatched signals/session +0.579 in the recent block (limit 0.5). Net points at cost 1 remain negative in all scenarios.
- Independent review findings on the 2026-11-07 round (documented, files not altered): `end < 7` undercounts
  "ended before first possible signal" (20 not 16); session 2026-09-11 silently absent from the 116-session input;
  early-close handling untested on data; no leakage found.
- Data: the 116 sessions (2026-05-19..2026-11-04) are **consumed**. The frozen-forward archive matches them with zero
  close difference on 2026-10-22..11-04 and declares `delayed=900` -> classify as DELAYED / RESEARCH_ONLY.
  Only one complete unconsumed session (2026-11-05) is available in-repo; 2026-11-06 is incomplete (70/78 bars).
- Network from cloud sessions: Yahoo is blocked by the proxy; no new data was fetched.

## Data acquisition status (2026-11-08)

- Collector `research/spx_collection/collect_yahoo_spx.py` works from this environment (Yahoo `query1/2.finance.yahoo.com` allowed; 7 tests pass). Pulled 7 complete 1m sessions 2026-10-29..11-06 with request/receipt times. Unused: 2026-11-05, 2026-11-06 (do not tune). Classification DELAYED_RESEARCH_ONLY; no per-bar receipt times exist.
- Yahoo serves only the last 7 trading days of 1m: pull at least weekly. `.github/workflows/spx_collect.yml` (daily 21:45 UTC) runs only after it reaches the default branch; untested on GitHub.
- Validation size (corrected, clustered bootstrap; see opening_seed/FAILURE_ANALYSIS.md): early-rate half-width +/-8.2 pp at 20 sessions, +/-4.9 pp at 54 (level only, no detectable dependence); the seeded-vs-control difference is +/-3.6 pp at 54, so ~70+ sessions to confirm a gain of the in-sample size.
- Random-timing baseline: "early" matches of both detectors are not clearly better than random timing; "matched before 75%" is.

## Checkpoint (2026-11-08, owner priority: SPX detector research)

- Deferred, not started: multi-provider router, external skills search, further team infrastructure.
- Experiment 2 `objective_review_20261107/threshold_scale/` (R = max(5, 0.67*ATR6)): REJECT by preregistered rule (older matched<=75% 134 vs 135). Early matches 48->65 overall (+17.4 over random vs +4.8 for control) but net execution points worse (-714.8 vs -440.2). Not rescued.
- Scheduled collector DISABLED after two fired test runs failed: (1) plain clone -> `fatal: could not read Username for 'https://github.com': terminal prompts disabled`; (2) `mcp__claude-code-remote__add_repo` not available in the routine session. Routine sessions have no repo source/credentials and the routine tool cannot attach one. Fresh-clone collection from an interactive session works (commit c26e456, raw hashes and `--verify` OK).
  Smallest fix: merge `.github/workflows/spx_collect.yml` to main (uses GITHUB_TOKEN), or recreate the routine in the claude.ai routines UI with this repo as its source. Until then collect manually; Yahoo keeps 7 trading days of 1m, so 2026-11-09 is lost if not pulled by 2026-11-17 after the close.
- `threshold_scale` is frozen at commit 91880b0 (a tag push was refused by the remote). Do not reconsider it with sessions after 2026-11-04.

## Missing for a real out-of-sample test

1. Complete regular-session SPX 1m (or 5m) OHLC for **unused** sessions after 2026-11-05 (>= 20 sessions recommended),
   same schema as `opening_validation_raw.json` (`day`, `step`, `csv` with `time,open,high,low,close`, NY wall clock).
2. Per bar: provider market timestamp **and** receipt timestamp, plus source/contract identity, to measure data age.
3. For any option claim: verified live SPXW chain with bid/ask, receipt time and entitlement status. None exists now.

## Next step

Do not retune on the 116 consumed sessions. Collect unused sessions, freeze the control wave detector (and, if desired,
opening_seed as a separately labeled challenger) and evaluate both on them with the same preregistered rule.

---

## Historical notes (2026-10-24, kept for reference; superseded where they conflict with the section above)


**Status: NOT READY** (ready for *connection/health verification only*; not ready for live early-detection use)

Last examined: 2026-10-24  
Latest commit before this update: `5cfb97f797e538b5dfa6e7a80cf9a1b8428b9d6e`

## Verification readiness (what "جاهز للتحقق" means here)

The project is prepared so the owner can **verify infrastructure and data path**, not so that detection is claimed working.

### Can verify today (Saturday — market closed)

| Check | Expected | Notes |
| --- | --- | --- |
| IBKR account connector | Connected | Account summary readable (2026-10-24 probe) |
| Flow type | REVIEW_AND_APPROVE | No autonomous live orders from this path |
| SPX index contract resolve | contract_id 416904 @ CBOE | `search_contracts` OK |
| SPX live snapshot | **REJECT** (top-status) | Expected on weekend / missing entitlement / frozen; do not treat as live edge |
| Software unit tests | Pass offline | No market required |
| Shadow / fail-closed on stale data | Can be exercised on saved data | Do not enable experimental Telegram alerts |

### Requires open RTH (or confirmed live session)

| Check | Required evidence |
| --- | --- |
| SPX cash last-trade timestamp freshness | Positive trade `ts` ≤ ~10s repeatedly |
| Option book sample (nearby SPXW) | Repeated callbacks, uncrossed bid/ask, age limits |
| Continuous collector heartbeat | Same-host IB Gateway + runner, not chat-only connector |
| Early-detection quality | New unconsumed dates + measured lead/false/miss vs baseline |

Until those open-session checks pass with retained logs, keep **NOT READY** and alerts **OFF**.

## What is already done (evidence)

- Issue #16 research preserved under `artifacts/issue16/`.
- Selected rule on spent holdout: low early recall; Yahoo bars ~9–10 min old.
- Canonical runtime with SETUP/TRIGGER/INVALIDATION/EXIT, cooldown, dedupe, stale fail-closed.
- Experimental alerts **OFF**.
- `spx_primary.py` / Gateway SPX path documented in `docs/SPX_PRIMARY_AND_PINE.md`.
- Active Telegram production path documented as separate repo `SuhailAlyami/spx-agent`.

## Why still NOT READY

1. **Feed timing / entitlement**: Free delayed futures and Saturday SPX snapshot REJECT do not prove timely cash SPX.
2. **Detection quality**: No generalized early edge on independent holdout.
3. **Host**: Chat IBKR connector ≠ always-on collector for Actions/runtime. Gateway on owner machine helps only while that machine stays up and authorized.
4. **SPX + options**: Live freshness and repeated option-book evidence not yet retained for open session.

## Data already consumed

- Holdout Oct 12–16 (RTH) and Oct 13–16 (all-session) are **spent**. Do not retune on them.

## Owner actions for full verification week

1. Keep IB Gateway running on a machine that stays on through the session you want to test.
2. On next open RTH: capture SPX last + top-status + receipt time; sample nearby SPXW books; save journals under a dated `artifacts/` folder.
3. Only after repeated fresh SPX trade timestamps: run shadow (no user alerts) for multiple sessions.
4. New research protocol only on **unconsumed** dates if claiming improvement.

## Resume command

```text
Read RESUME.md + docs/ISSUE16_REPORT.md + AGENTS.md + docs/SPX_PRIMARY_AND_PINE.md.
Confirm experimental alerts OFF.
If Gateway is up on open RTH: verify SPX top-status + last ts age, then shadow only.
If Saturday/closed: only connection + offline tests; do not claim live detection.
```

## Change log

- 2026-10-24 (earlier): Initial RESUME.md from repo exam.
- 2026-10-24 (this update): Verification checklist; IBKR chat connector account OK; SPX snapshot top-status REJECT on Saturday; still NOT READY; alerts remain OFF.
