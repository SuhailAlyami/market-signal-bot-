# RESUME.md — Suhail Hunter

**Status: NOT_READY / RESEARCH_ONLY.** Alerts OFF. No real trading. Next-session direction/high/low forecasting is a separate experiment.

Last updated: 2026-11-08 (branch `claude/kind-ramanujan-icu95e`, based on open PR #51 head `446add9`).

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
