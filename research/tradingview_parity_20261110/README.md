# Can the frozen detector run on TradingView CAPITALCOM:SPX500 via Pine? — difference record (2026-11-10)

Status NOT_READY. Nothing in the detector, the collector, the collected data or the frozen forward test was changed. This is a documented difference list and a minimal manual test plan for review. No Capital API, no subscription, no webhook, no alerts.

## What was inspected
- Frozen logic: `research/breadth_20261109/breadth_core.py` (wave detector from `objective_review_20261107/wave_capture/run.py` + agreement of 10 stocks), protocol `fc4f002`, forward protocol on main (418d121).
- Existing Pine: `tradingview/Suhail_Hunter_CAPITALCOM.pine` (PR #51 branch) is a DIFFERENT older rule (`hunter-cfd-tickvolume-v1`, 1-minute, prior-20 levels, broker tick volume). It is not the frozen detector. `tradingview/Suhail_Hunter_ES.pine` (main) is also a different rule and rejects CFD symbols on purpose.
- Prior CFD evidence (PR #51, `docs/CAPITALCOM_RESEARCH.md`, `docs/CFD_DIAGNOSTIC_RESULT_20261029.md`): Capital.com states extended index-CFD prices are based on live futures and may differ from the cash index; the signed-in free account showed ~1 update per second, but **script saving and technical alerts were blocked by the plan**; no data export was retained.

## Differences between the frozen rule and a Pine run on CAPITALCOM:SPX500
| # | Frozen rule (validated input) | CAPITALCOM:SPX500 on TradingView | Consequence |
|---|---|---|---|
| 1 | ^GSPC cash index (Yahoo), DELAYED_RESEARCH_ONLY | Broker CFD; pricing may follow futures; basis vs cash unknown | Same thresholds (5-pt floor, ATR6 in points) may trigger at different bars. Must measure basis first. |
| 2 | XNYS regular session only, per-session reset, 6-bar warm-up from 09:30 | ~24 h instrument | Pine must mask to 09:30-16:00 New York and reset state each session; DST is handled by the NY timezone, but early closes (e.g. 2026-11-27 13:00) are not known to a session string and need an explicit date list. |
| 3 | 5-minute bars labelled by start, closed-bar decisions | Pine recalculates on every tick of the live bar | Evaluate only on `barstate.isconfirmed`; signal = bar close; entry = next bar open. Otherwise signals repaint. |
| 4 | Breadth: 10 stock closes at the same 5m close and 15 min earlier | `request.security` per stock; on a live bar it returns the stock's forming bar | At chart-bar close the stock bar may not have its final tick; free-plan stock data may be delayed (unknown, must be read off the probe). Approximation until a parity check passes. |
| 5 | Agreement needs all 10 stocks present | Missing/halted symbol returns `na` | Must drop the signal (as Python does), never fill. |
| 6 | Forward test is defined on ^GSPC Yahoo data | CFD is a different universe | CFD/Pine results can NEVER count toward the frozen forward test. |
| 7 | Volume not used by this rule | CFD "volume" is broker tick count | No issue for this rule. |

## What can and cannot be linked automatically without a webhook
- Can: show the probe/table on the chart; owner reads values or takes screenshots; TradingView's own (possibly paid/limited) notifications if the plan allows.
- Cannot: send chart signals or prices to GitHub/the repository automatically; schedule unattended evaluation; verify delivery latency. The prior free-account session could not save scripts or create technical alerts. Data export on the current plan is unverified.
- Therefore any Pine result is a manual observation, recorded by hand, not a measured live system.

## Minimal test plan on the free chart (manual, 3 steps; stop at the first failure)
1. **Feed probe (5 min, during 17:30-00:00 Riyadh).** Paste `feed_probe.pine` on CAPITALCOM:SPX500, 5-minute. Record the table once: chart symbol, timeframe = 5, regular session = yes, live/forming, updates in bar (rising), basis vs SP:SPX, and ages. Pass if all 11 symbols resolve and every age is below 300 s (one bar). If SP:SPX or any stock is missing or older than 900 s, breadth cannot run live on this plan: stop and record.
2. **Parity on consumed dates (after this record is reviewed).** A Pine port of the frozen rule, run on **SP:SPX** 5-minute (not the CFD), must reproduce the 27 reference signals in `reference_signals.json` (2026-10-29..11-04, consumed, outcome-free: time, side, R, agreement). Pass = 27/27 identical time and side, agreement within 0. Any difference is documented before anything else changes.
3. **CFD drift (only if step 2 passes).** Same port on CAPITALCOM:SPX500 for the same dates: count matching signals and the basis per day. This measures drift only; it does not validate the detector.
No alerts in any step. A passing step means "the chart can reproduce the frozen rule", not that the detector works or is real time.

## Not verified here
The Pine probe was not compiled (no Pine compiler in this environment). TradingView data delays, plan limits and export availability on the owner's account must be read from the chart itself.
