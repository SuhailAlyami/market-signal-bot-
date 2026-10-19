# Issue #16 — measured early-detection report

**Decision: NOT READY. Experimental alerts remain OFF.** No verified actionable
SPX 0DTE advantage was demonstrated. The selected detector misses most events,
the early-signal advantage does not hold across instruments/baselines, and
observed Yahoo futures candles arrive too old for this short-horizon goal.
Software tests and HTTP uptime are separate evidence.

## Retained data and protocol

Actual no-cost Yahoo/yfinance snapshots contain 27,336 ES and 27,337 NQ one-minute
rows, from 2026-09-21 00:00 UTC through 2026-10-18 23:59 UTC. See
[acquisition metadata](../artifacts/issue16/data/acquisition.json) for exact row
counts, request windows, observed times, dependency versions and raw SHA-256.
These are continuous futures proxies, not resolved tradable contracts or a
point-in-time publication archive. No data was filled or synthesized.

RTH research uses 09:30–16:00 America/New_York. There are 20 fully bounded RTH
dates: train September 21–October 2 (10 sessions), validation October 5–9
(5), untouched holdout October 12–16 (5). The all-session variant has 16 fully
bounded sessions (8/4/4); its holdout is October 13–16. Monday Globex sessions
lacking required observed boundaries are excluded, rather than imputed. Exact
session inventories and timestamp partitions are retained. The RTH definition is
a fixed research window; exchange-holiday completeness comes from observed
boundaries. Runtime separately uses the CME exchange calendar.

Twenty declared candidate configurations span level proximity (previous session,
rolling range, completed 15m opening range), contraction/expansion, acceleration,
failed breakouts, and 5m/15m trend plus relative volume. Expanding folds use only
training prefixes to fit volume cutoffs and rank candidates. The top two per
method reach validation; validation **early-event F1** selects the frozen method
and parameters. No threshold is refitted on validation/test. Every evaluation
applies a 10-minute embargo on both partition edges and requires outcome labels
to stay within their partition. The selected method in all four studies was
`failed_breakout`, with RVOL >=1.0; full fitted parameters, train folds and
validation scores are in each JSON report.

An independent movement event is the first directional high/low touch of
`max(0.06% of anchor close, 2 * prior 20-bar ATR)` within 10 subsequent minutes.
Onset is the first **completed close** reaching 25% of that target. Ambiguous
two-sided touches in one bar are excluded. Greedy event windows do not overlap.
One direction-matched signal can detect one event. A completed signal/delayed
receipt must occur by the **start** of the target minute; a close after that
target touch cannot earn credit. Lead is onset-close time minus decision time;
positive lead counts as early. These engineering labels are not external market
truth and do not measure whether option premiums already inflated.

Candidate generation and 10-minute cooldown use past data only, even when a
future outcome later proves missing. Such signals remain in CSV artifacts as
censored and do not enter precision denominators. Invalid OHLCV/zero-volume
rows, incomplete candles and gaps cannot become setups or historical levels.
The retained sources contain 25 invalid ES rows, 24 invalid NQ rows, and 54 gaps
longer than one minute in each source. Unknown-outage movements remain unobservable, not assumed
correct or incorrect.

## Untouched holdout: selected candidate

All figures below first assume a theoretical decision immediately after the
completed candle. “P/R” means event precision/recall; early P/R uses only positive
lead. Median lead includes all matched events, including post-onset matches.
False/session and misses use the broader event match; early misses are worse.

| Study | Sessions | Events | Scored signals | Early detections | Event P/R | Early P/R | Median lead min | False/session | Missed events |
| --- | ---: | ---: | --- | ---: | --- | --- | ---: | ---: | ---: |
| ES RTH | 5 | 121 | 47 (+3 censored) | 5 | 17.02% / 6.61% | 10.64% / 4.13% | 1.5 | 7.80 | 113 |
| ES ALL | 4 | 240 | 105 (+0 censored) | 11 | 15.24% / 6.67% | 10.48% / 4.58% | 1 | 22.25 | 224 |
| NQ RTH | 5 | 143 | 59 (+2 censored) | 2 | 16.95% / 6.99% | 3.39% / 1.40% | 0 | 9.80 | 133 |
| NQ ALL | 4 | 373 | 140 (+4 censored) | 12 | 18.57% / 6.97% | 8.57% / 3.22% | 0 | 28.50 | 347 |

RTH early misses are **116/121 ES** and **141/143 NQ**. ES has 42/47 scored
signals without an early match; NQ has 57/59. Censored signals are not hidden:
RTH ES scheduled 50 total, NQ 61; respectively 3 and 2 lack a fully observable
horizon in the phase. RTH eligible scored anchors total 1,880 minutes each;
all-session totals 4,884 each. See the retained signal/event/split CSVs for each
individual detection and missed event.

## Baselines and uncertainty

These baselines were declared before the holdout: no signal, simple 5m trend
persistence, and completed 20-bar breakout with RVOL >=1.3. All use the same
causal scheduling, cooldown, event universe, embargo and censoring. They were
published for comparison, never used to switch detectors after test inspection.

| Instrument RTH | Rule | Scored signals | Event P/R | Early P/R | False alarms | Misses |
| --- | --- | ---: | --- | --- | ---: | ---: |
| ES | selected failed_breakout | 47 | 17.02% / 6.61% | 10.64% / 4.13% | 39 | 113 |
| ES | no_signal | 0 | — / 0.00% | — / 0.00% | 0 | 121 |
| ES | trend_persistence | 188 | 27.66% / 42.98% | 9.57% / 14.88% | 136 | 69 |
| ES | breakout | 66 | 27.27% / 14.88% | 4.55% / 2.48% | 48 | 103 |
| NQ | selected failed_breakout | 59 | 16.95% / 6.99% | 3.39% / 1.40% | 49 | 133 |
| NQ | no_signal | 0 | — / 0.00% | — / 0.00% | 0 | 143 |
| NQ | trend_persistence | 188 | 32.45% / 42.66% | 9.57% / 12.59% | 127 | 82 |
| NQ | breakout | 74 | 33.78% / 17.48% | 5.41% / 2.80% | 49 | 118 |

ES shows a descriptive early-metric increase over the breakout rule, but the
trend baseline captures more early events and has higher early F1. NQ's selected
rule performs worse than both nonzero baselines in early F1. There is no
consistent demonstrated advantage. The no-signal baseline avoids all false
alerts while missing all events; it is not a prediction success.

| Selected | Event precision 95% | Event recall 95% | Early precision 95% | Early recall 95% | Median lead session-bootstrap 95% |
| --- | --- | --- | --- | --- | --- |
| ES RTH | 8.89%–30.14% | 3.39%–12.51% | 4.63%–22.59% | 1.78%–9.31% | [0.0, 2.0] min |
| NQ RTH | 9.48%–28.46% | 3.84%–12.39% | 0.93%–11.54% | 0.38%–4.96% | [-2.0, 0.0] min |

Intervals are Wilson binomial estimates plus 500 deterministic session-block
bootstrap samples (seed16). Full reports retain CIs for all metrics/baselines.
Five RTH/four all-session holdout sessions are small and correlated; Wilson
independence is imperfect and bootstrap bounds are descriptive. ES's lead-time
interval includes zero. No statistical-significance or profitable-edge claim is
made. No prices, fills, commissions, spread, slippage or option P&L are simulated:
this is classification research, not a cost-adjusted trading backtest.

## Actual availability and delay sensitivity

[Repeated source observations](../artifacts/issue16/feed_observations.json)
record actual active-session ES/NQ latest-completed-bar ages around 9.4 minutes,
with request durations separately retained. Live shadow receipts likewise showed
roughly 9–10-minute-old data. Yahoo's documentation specifies a CME delay of
10 minutes; see the [lawful source review](DATA_SOURCES.md). This is completed-bar
age evidence, **not exact provider publication latency**, historical arrival
proof, independent feed validation, or verified live-feed entitlement.

The frozen study adds 0/5/10/15 minutes to the theoretical signal timestamp.
At +5 minutes, **early recall is zero in all four selected studies**, with
remaining RTH matches arriving median 3 minutes after onset for ES and 4 minutes
after onset for NQ. At +10/+15, no selected detections precede the target-minute
start. That follows this particular ten-minute event horizon; it is not a
universal claim about all possible future strategies. Scheduler/poll latency
would add further delay. No delayed bar is relabeled real time.

## Runtime, shadow record, and software health

One canonical completed-1m runtime now replaces the independently launched
Render/Actions scanners. Detection runs without Telegram credentials, independently
of outbound alert quotas. Experimental outbound events cannot be enabled by an
environment flag. The archived detectors remain available for research only.
The shadow runtime retains the experimental `pre_level` rule using the shared
causal features. The selected `failed_breakout` research result was not promoted
to a verified production detector because it did not establish an advantage.

The shared causal feature code supports SETUP / TRIGGER / INVALIDATION / EXIT,
two buffered confirmation closes, cooldown, dedupe, atomic state, and shadow
observations. Receipt-time calendar and freshness checks fail closed for stale,
malformed, missing, incomplete, zero-volume or provider-failure data. Restart gaps
cancel unsafe active scenarios. Confidence remains explicitly uncalibrated;
there is no fabricated probability or SPX strike/premium/fill.

[Actual live shadow journal](../artifacts/issue16/live_shadow/shadow.jsonl) and
[local application journal](../artifacts/issue16/local_app/shadow.jsonl) record
`REJECTED` stale-feed decisions and heartbeat with actual receipt times and last
completed candle. No timely feed meant **zero valid live setups and zero resolved
live trade outcomes**. These records demonstrate outage observability, not
predictive success. Future valid paper decisions have five complete subsequent
minutes measured after their actual detection time; their first Open is labeled
a diagnostic reference, never a fill. There are no automatic orders.

[Local HTTP observation](../artifacts/issue16/local_app/health.json) returned200
for process liveness while exposing degraded/stale feed health and NOT READY.
`/health` also reports heartbeat age/stalled worker status. The local process
was stopped after verification; it is not evidence that the PR is deployed.
Atomic files survive process restarts on a retained filesystem; free Render
replacement may erase them. Actions cache/retention/scheduling are best effort.
No paid resource or storage was created.

Render deployment health remains **UNVERIFIED**. MCP access had no selected
workspace, and repository deployments API access returned403. The Render
[access reference](skill://plugin_asdk_app_6a624c56bfe081918f7544f7d58f6faf/render-monitor/references/render-access.md)
says: “If no workspace is selected—or if the intended workspace is ambiguous—list
the available workspaces and have the user identify the correct one.” This task
continued through research, local runtime verification and PR creation without
switching an unconfirmed workspace or claiming deployment success.

Actual software verification: **60/60 deterministic tests passed** on
Python3.11.17 with the pinned application/research dependencies; compileall passed.
[Verification log](../artifacts/issue16/verification.log) and
[metadata/hashes](../artifacts/issue16/software_verification.json) are retained.
Coverage includes holdout mutation, future-feature leakage, causal censoring,
DST, holidays, openings, stale feeds, transition hysteresis, restart gaps,
duplicate reservations, provider/calendar/persistence failures and receipt-time
outcome handling. Five legacy tests silently skipped by unittest are now
actually discovered. Research/runtime code review corrected the defects listed
below; passing these checks does not guarantee defect-free operation. GitHub's
PR checks separately reproduce the
full retained reports and run application regressions. Their status is code and
reproducibility evidence, not prediction accuracy.

## Reproduce and preserve

Use Python3.11 and [the exact research package lock](../artifacts/issue16/requirements-research.txt),
then run the two offline commands in [README](../README.md). No provider request
is needed to reproduce the published four reports. The dedicated PR workflow
reruns and compares complete JSON reports with these retained measurements.
The [artifact manifest](../artifacts/issue16/manifest.json) fingerprints retained
inputs, reports, event/signal/split CSVs, shadow observations and verification.

Full outputs: [ES RTH](../artifacts/issue16/research/es/rth_report.json),
[NQ RTH](../artifacts/issue16/research/nq/rth_report.json),
[ES all-session](../artifacts/issue16/research/es/all_report.json),
[NQ all-session](../artifacts/issue16/research/nq/all_report.json).
The [previous weak pilot](../artifacts/issue16/previous_pilot/) was also preserved
from its actual Actions stdout when artifact-blob download was denied.

Correctness defects found before publication were repaired before the final run:
future-dependent signal scheduling, same-target-bar close credit, invalid
historical reference levels/training rows, timestamp units and gap recovery.
The first benchmark processes were stopped before any report was emitted; no
holdout result was used to tune the published method. This holdout is now spent:
future detector changes require new unseen dates or an independently frozen
forward study, not repeated tuning on October12–16.

## Remaining product gap

Issue#16 is **not closed as product-ready**. The engineering/research deliverables
are implemented and preserved, but a timely underlying source, legitimate live
SPX chain, retained multi-session forward shadow evidence, durable operational
state and independently demonstrated improvement are still absent. Continue
research with alerts off and a newly frozen protocol/unseen dates. No subscription,
real-money order, invented quote, or prediction-certainty claim is necessary.
