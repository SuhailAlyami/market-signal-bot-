# Half-minute early-detection pilot — 20 October 2026

**Decision: NOT READY. Neither new candidate is promoted to runtime or alerts.**

This experiment addresses detector latency rather than deployment status. It
compares completed 30-second observations against the frozen minute rule and a
basic breakout, using actual IBKR native futures history. It does not model SPX
option returns, books, execution or profit.

## Freeze and acquisition

Rules, causal regression tests, thresholds,
methods and a common cutoff were committed before obtaining the half-minute
inputs: `c4c0ea1ebf851c0fc02176f7672aa62da662c53d`. Two fixed candidates:

- Pressure SETUP: completed-half relative volume >=1.5 against the prior 40
  halves, within 0.3 prior ATR of a 20-completed-minute level, prior contraction
  <=0.55, current impulse >=0.1 ATR, prior trend and exact-time companion agree.
- Release: same liquidity/trend/companion checks, price beyond the prior level,
  current impulse >=0.15 ATR. Both use a 10-minute causal candidate cooldown.

The 30-second observations never form their own prior-minute reference levels.
Only complete 00s/30s pairs may construct a minute. Missing counterpart bars,
zero volume, malformed OHLCV and insufficient contiguous history block signals.
No parameters are fitted or selected on these results.

IBKR ONE_DAY returned the current CME trading day, 19 October 22:00 UTC to the
morning of 20 October, which contains no completed New York session. The
zero-RTH result and raw inputs are retained. A coverage-only amendment was
committed before requesting a prior completed session:
`b0e98958a62e34c8eee91cae409968932dc08494`. The TWO_DAYS request returned provider
errors. The originally declared bounded 1000-bar fallback with outside_rth=false
returned real 30-second arrays covering a short post-NY period on 16 October
and 19 October 13:30–20:59:30 UTC. No pagination or provider-limit bypass was used.

Only 19 October contributes NY evaluation. Each symbol has 350 eligible minutes
and 29 canonical events after history warmup and the future-outcome horizon.
The first 30 NY minutes lack a valid contiguous historical warmup in this
RTH-only download and are not scored. Different-expiry futures contracts
are not interchangeable with continuous historical futures; actual contracts
in this acquisition are December 2026. Related ES/NQ and already examined
market dates are not independent sessions. This is a one-session retrospective
pilot, not independent validation and not a historical 0DTE options study.

## Timing correction after inspecting initial outputs

The first pilot compared half-minute signals to minute-close onset. That can
artificially credit a half-minute detection after the first half had already
reached the onset threshold. The original output remains
`minute_resolution_report.json`. After observing it, timing was corrected:

- Keep the same canonical events, directions, anchors, +/-max(6bp,2 prior ATR)
  target distance and 10-minute horizon for every method.
- Refine onset to the first completed 30-second close reaching 25% of the target.
- Refine the deadline to the START of the first target-touch 30-second bar.
- Apply these same finer timestamps to minute and half-minute candidates.
- Delivery delays never move a signal generated before the event's anchor into
  eligibility. Candidates consume cooldown before future-data censoring.

This evaluation change happened after initial result inspection and is recorded
in `timing_amendment.json`; it is not called an untouched test. Candidate
parameters are unchanged. Source and parameter fingerprints are checked before
reproduction. A regression demonstrates the removed artificial early credit.

## Corrected results with 30 seconds added delivery delay

| Instrument/method | Signals | Matched / 29 | Before onset | Within first minute or before | False alarms |
| --- | ---: | ---: | ---: | ---: | ---: |
| ES half pressure | 3 | 1 | 0 | 0 | 2 |
| ES half release | 12 | 3 | 2 | 2 | 9 |
| ES frozen minute rule | 4 | 0 | 0 | 0 | 4 |
| ES basic minute breakout | 11 | 2 | 0 | 1 | 9 |
| NQ half pressure | 3 | 2 | 0 | 1 | 1 |
| NQ half release | 13 | 3 | 0 | 2 | 10 |
| NQ frozen minute rule | 0 | 0 | 0 | 0 | 0 |
| NQ basic minute breakout | 12 | 4 | 1 | 3 | 8 |

The ES half release has two early matches out of 29 events, with nine false
alarms out of twelve candidates. Its matched-event precision is 25%; early
precision is 16.7%, and early recall is 6.9%. Neither apparent timing benefit
nor a small NQ pressure sample establishes a usable edge. At 60 seconds added
delay, both new candidates have zero early matches on both instruments.
The basic breakout retains one NQ early match at that delay. Full 0/15/30/60
second sensitivity, timestamps, Wilson intervals, censored samples and all
missed events remain in the report. Median lead can improve when late matches
drop out at higher delay; this is selection among remaining matches, not a gain.

## What the misses reveal

The report includes a per-event audit of causal observations between anchor
completion and refined onset. Of 29 events per symbol, onset arrives within 30
seconds for 3 ES and 7 NQ events; within 60 seconds for 13 ES and 15 NQ events.
Under this matching protocol a new completed observation cannot precede onset
for those fastest cases. This is a timing limitation, not predictive proof.

For the missed early release events, at least one pre-onset opportunity fails
the prior-level release condition in all 27 ES misses and 26 of 29 NQ misses.
Relative-volume, current impulse and companion confirmation frequently fail as
well. These counts are overlapping mechanical rejection gates, not independent
causal explanations. Removing those gates after viewing this day would be
in-sample tuning; no such rule change or claimed validation is made here.

Half-minute sampling alone does not solve missing inside-range turns, false
alarms, late delivery or option-book execution. A valid next experiment must
freeze any new hypothesis and measure it on future sessions without selecting
on this same day again. No reliable early SPX 0DTE detector is established.

## Reproduction and operational scope

```bash
python halfminute_research.py \
  --es artifacts/halfminute-pilot/es_rth_raw.json \
  --nq artifacts/halfminute-pilot/nq_rth_raw.json \
  --cutoff 2026-10-20T08:54:00+00:00 \
  --output /tmp/halfminute-result
```

`ibkr_market_data` now supports the actual THIRTY_SECS provider step. Explicit
bounded collection is available through:

```bash
python acquire_hunter_data.py --interval 30s --output halfminute-capture
```

This uses the host's existing IBKR authorization. It creates no authorization,
uses no Yahoo fallback, and does not automatically activate the experimental
30-second rules. Alerts stay OFF; the deployed minute collector is unchanged.
