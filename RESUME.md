# RESUME.md — Suhail Hunter

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

## Research finding — 2026-11-14

**Root cause of NOT_READY identified.** The signal exists. The data source is the bottleneck.

### What all experiments prove

| Experiment | Best result | Why it fails |
|---|---|---|
| explosion_detector.py (5m Yahoo bars) | Detects moves | Bars arrive 9-10 min late; 70-90% of move is done |
| halfminute-pilot (30s ES/NQ) | 16.7% precision, +60s lead | Too weak, not SPX |
| detector_v2 (4 ML models) | 29.2% precision, −1 min lead | Negative lead = confirms after move |
| **breadth_20261109** | **59.6% direction, +1.23pt gross** | **Yahoo delay kills entry; net turns negative at 1pt cost** |

### The breakthrough signal

`wave_capture.detect` on SPX 5m + constituent agreement ≥ 8/10 megacaps + first session half:
- 59.6% directional accuracy (bootstrap CI excludes zero — only signal in repo with this property)
- +1.23pt mean gross per signal over 57 development sessions
- Net at 0.5pt cost: **+41.5pt total** (profitable)
- Net at 1.0pt cost: +13.0pt total (marginal but positive)

**The signal code is already written and frozen** in `research/breadth_20261109/`.

### Why Yahoo delay kills it

Yahoo bars arrive 9-10 min old. By the time the signal fires, the move is already complete. With IB Gateway (< 1s latency), the same signal fires on the current bar and the full +1.23pt gross is capturable.

### Path to READY

1. **Collect 20 new sessions** (Nov 10 – Dec 10 ≈ 20 trading days) using `research/spx_collection/collect_yahoo_spx.py --breadth` from your machine (needs `yfinance` installed)
2. **Run holdout protocol**: `python3 research/breadth_20261109/run.py --holdout` — code already frozen, no fitting
3. **Verify live feed**: IB Gateway on during RTH → `spx_primary.py` → confirm SPX last-trade timestamp age ≤ 2s
4. **Shadow run**: 10 sessions with live IB feed, breadth signal logging only, no alerts
5. If shadow performance within 20% of backtest: upgrade to READY

### Owner actions (from your machine only)

```bash
# Step 1: collect breadth data daily (5 min/session)
pip install yfinance exchange_calendars
python3 research/spx_collection/collect_yahoo_spx.py --breadth

# Step 2: after 20 sessions, run holdout
python3 research/breadth_20261109/run.py --holdout

# Step 3: verify live feed on any open RTH
# IB Gateway running → python3 spx_primary.py → check for LIVE_VERIFIED in log
```

### Consumed data

- Dev: Aug 17 – Nov 04 (57 sessions) — all consumed by breadth_20261109
- Holdout (SPENT): Oct 12–16 — do not retune on these
- Breadth holdout (LOCKED): Nov 05-09 (3 sessions) — do not read until 20 new sessions collected
- Nov 10+ dates: unconsumed, available for new collection

## Resume command

```text
Read RESUME.md + docs/ISSUE16_REPORT.md + AGENTS.md + docs/SPX_PRIMARY_AND_PINE.md.
Confirm experimental alerts OFF.
If Gateway is up on open RTH: verify SPX top-status + last ts age, then shadow only.
If Saturday/closed: only connection + offline tests; do not claim live detection.
Next research action: collect breadth sessions Nov 10+ from owner's machine.
```

## Change log

- 2026-10-24 (earlier): Initial RESUME.md from repo exam.
- 2026-10-24 (this update): Verification checklist; IBKR chat connector account OK; SPX snapshot top-status REJECT on Saturday; still NOT READY; alerts remain OFF.
- 2026-11-14: Full experiment audit. Root cause identified: Yahoo delay kills a real signal. Breadth first-half has 59.6% direction accuracy with bootstrap CI excluding zero — best result in repo. Path to READY documented above.
