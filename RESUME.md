# RESUME.md — Suhail Hunter

**Status: NOT READY**  
Last examined: 2026-10-24 (Grok session)  
Base commit: `0564c0667be0373a65831c2d514bf51a378ed9bf` (main, 2026-10-22)

## What is already done (evidence)

- Issue #16 research completed and preserved under `artifacts/issue16/`.
- Selected research method (`failed_breakout` + RVOL) on untouched holdout:
  - ES RTH early recall ≈ 4.13%, precision ≈ 10.64%; most events missed.
  - NQ RTH early recall ≈ 1.40%; worse than simple baselines on early F1.
  - Yahoo/CME completed bars observed ~9–10 min old → early detection destroyed for short-horizon labels.
- Canonical runtime (`hunter_runtime.py`) exists with causal features, SETUP/TRIGGER/INVALIDATION/EXIT, cooldown, dedupe, stale-data fail-closed, shadow journal.
- Experimental alerts remain **OFF**. No promotion of the research detector.
- Software regressions: 60/60 deterministic tests reported passing at Issue #16 close-out; plan-rejection lifecycle tests added later.
- Active production Telegram path is documented as the separate repo `SuhailAlyami/spx-agent`.
- Multiple docs: AGENTS.md, ISSUE16_REPORT.md, OPERATIONAL_READINESS.md, DATA_SOURCES.md, HUNTER_INVENTORY.md, etc.

## Why still NOT READY (evidence-based)

1. **Feed timing**: Lawful free Yahoo futures data arrives too late for the defined early-event horizon. No verified timely SPX cash source is integrated and proven continuous.
2. **Detection quality**: Selected rule does not beat relevant baselines consistently on early metrics; sample of holdout sessions is small.
3. **Operational host**: No proven always-on authorized IBKR collector reachable by scheduled runners. Missing `IBKR_RUNNER` is now visible as `COLLECTOR_NOT_CONFIGURED` rather than silent skip.
4. **SPX cash + options**: Goal is cash SPX early explosion + eventual 0DTE context. Current retained research is ES/NQ futures proxies. No verified live option chain.

## Data already consumed

- Holdout windows Oct 12–16 (RTH) and Oct 13–16 (all-session) are **spent**. Do not retune on them.
- Any future claim of improvement requires new unseen dates or a freshly frozen forward protocol.

## Current blockers that need owner action

- Provision or confirm an authorized host that can keep IB Gateway / session alive and expose a runner secret for GitHub Actions (or equivalent free continuous path).
- Confirm whether the product priority remains cash SPX (vs ES/NQ futures research) and whether any new free/timely data source is acceptable.

## Next safe step (do not skip)

1. Do **not** enable experimental alerts.
2. Do **not** retune on the spent holdout.
3. If a new timely SPX cash (or confirmed lower-latency) source becomes available, freeze a new protocol + new date range before any parameter search.
4. Otherwise continue research offline on any remaining unused historical windows, or acquire fresh bounded data with explicit as-of timestamps, keeping alerts off.

## Resume command (when returning)

```text
Read RESUME.md + docs/ISSUE16_REPORT.md + AGENTS.md.
Confirm no experimental alerts are enabled.
If IBKR collector host is now available, verify heartbeat + freshness before any live shadow.
Otherwise stay in research-only mode on unconsumed data.
```

## Change log for this file

- 2026-10-24: Initial RESUME.md created from repository examination. No code or detector changes. Status remains NOT READY.
