# SPX option-premium radar — first actual IBKR study, 20 October 2026

**Decision: NOT READY. No demonstrated early-prediction edge. Experimental
notifications remain OFF.** This change observes option premiums themselves,
rather than assuming an ES/NQ candle implies a particular SPX option return.

## Implemented observations

- `WATCH`: a completed one-minute trade candle rises toward the previous
  20-minute high after a short contraction, with relative volume >=1.2.
- `ACCELERATION`: a completed one-minute trade candle exceeds that high,
  rises at least max(3%, 1.5 times the preceding median absolute return),
  and has relative volume >=1.5. This observes a move already developing.
- Twenty consecutive past candles, valid finite OHLCV, at least 12 active
  volume bars and a positive-volume current candle are required. No candle
  filling, zero-volume triggers, unfinished candles or future inputs.
- Runtime assessment additionally requires REALTIME status and a last
  completed bar no older than 120 seconds. An observation is research-only;
  it never bypasses the independent executable bid/ask freshness gate.
- The opt-in IBKR collector requests 90 one-minute bars for CALL and PUT at
  its nearest resolved strike. The worker journals deduplicated observations
  and invalidations across restarts, including cancellation on provider outage,
  crossed reference level or ten-minute expiry. No Telegram sender is enabled.

## Actual retained sample and reproduction

Contracts: SPXW, 20 October 2026 expiration, 7690 CALL and 7690 PUT.
Actual `get_price_history` requests used TWO_DAYS / ONE_MIN / outside_rth=true.
CALL returned 1,507 rows; PUT returned 1,506. The interval starts at
2026-10-19 00:15 UTC and ends on 20 October around 04:41 UTC. New York calendar
dates span October 18–20 because overnight trading crosses date boundaries;
these are **not three independent full trading sessions**.

Raw parallel arrays and full descriptive JSON reports are retained under
`artifacts/premium_radar/`. Input hashes are included in each report.

```bash
python research_premium_radar.py --input artifacts/premium_radar/call_history.json --output /tmp/call_report.json
python research_premium_radar.py --input artifacts/premium_radar/put_history.json --output /tmp/put_report.json
```

A longer one-minute request was rejected by IBKR with an explicit data-point
limit. One-week requests with/without RTH also exceeded the applicable limit.
The missing history was not filled or invented. More sessions must be acquired
prospectively or through a separately supported historical-data path.

## Event and timing protocol

An event is a nonoverlapping 25% rise from an eligible option last-trade close
within the next five minutes. Onset is conservatively the START of the first
future minute whose high reaches +5%; the target deadline is the START of the
first +25% minute. Intrabar order/time is unknown. A signal at a completed close
after the target minute begins cannot receive detection credit.

Signal generation and five-minute cooldown precede future label checking.
Signals lacking contiguous, valid observable future bars are censored, not
credited as successes or automatically counted as losses. Fixed thresholds
were not optimized on this sample. Reported 0/60/120-second availability delays
are hypothetical sensitivity scenarios, not measured historical arrival times.

## Descriptive results at zero added delay

| Contract / method | Scored signals | Censored | Events detected | False alarms | Early detections |
| --- | ---: | ---: | ---: | ---: | ---: |
| CALL WATCH | 0 | 0 | 0 of 1 | 0 | 0 |
| CALL ACCELERATION | 1 | 0 | 1 of 1 | 0 | 0 |
| CALL basic breakout | 1 | 2 | 1 of 1 | 0 | 0 |
| CALL basic 3% momentum | 3 | 6 | 1 of 1 | 2 | 0 |
| PUT WATCH | 1 | 1 | 0 of 3 | 1 | 0 |
| PUT ACCELERATION | 4 | 3 | 0 of 3 | 4 | 0 |
| PUT basic breakout | 9 | 8 | 1 of 3 | 8 | 1 |
| PUT basic 3% momentum | 16 | 39 | 2 of 3 | 14 | 1 |

CALL acceleration's matched signal arrived **180 seconds after onset**, before
the target-minute deadline. At +120 seconds of added availability delay it no
longer matched the event. PUT acceleration missed all three scored events.
The new hypotheses do not beat the simple baselines consistently. One matched
CALL event is not a reliable precision estimate or a profitable strategy.

The sample cannot support chronological train/validation/independent holdout
partitions; `holdout` is explicitly null. Selected near-ATM contracts have
selection/survivorship bias and changing days-to-expiration/Greeks. Trade highs
are not executable bid/ask, fills or option P&L. Fees, spread and slippage were
not simulated. Publication/arrival times are absent from history. No calibrated
probability, validated predictive edge, subscription, order or profit is claimed.

## Remaining deployment and product requirements

The independent runtime OAuth authorization from PR #19 remains required.
Connecting ChatGPT's IBKR tool does not authorize Render automatically.
Collect more independent contracts/sessions and retain actual receipt times,
then freeze selection on training/validation and assess unseen future sessions.
Do not turn experimental observations into trade recommendations merely because
unit tests or API calls succeed.

## Follow-up: frozen search and separate-contract replication

The 7690 CALL/PUT pilot is now explicitly development data. An 18-point grid
combined relative-volume thresholds 1/1.5/2, one-minute returns 0.5/1.5/3%, and
maximum distance below the preceding high 0.5/1.5 median bar ranges. Price must
also be no more than two median ranges above that high and three-minute momentum
positive. Selection required at least three scored signals and maximized
`2 * early + during - false alarms`. Every trial assumed a 60-second additional
availability delay. These weights and thresholds are exploratory, not a fit of
probabilities. Reusing the small pilot for tuning invalidates any holdout claim.

The chosen setting (relative volume 2, one-minute return 3%, distance 1.5) was
committed BEFORE fetching the additional 7695 CALL/PUT histories. Frozen evidence:
commit `9a53b903b243da9bb7525ffe0706f5277b87b2ed`,
`artifacts/premium_radar/development_frozen.json`.
The grid's best development utility was **negative (-5)**; selecting a best
candidate is not evidence that it works.

| Sample | Scored signals | Matched events | Before onset | False alarms |
| --- | ---: | ---: | ---: | ---: |
| Development, 7690 CALL/PUT | 7 | 1 of 4 | 0 | 6 |
| Separate-contract replication, 7695 CALL/PUT | 5 | 0 of 2 | 0 | 5 |

Replication came directly from IBKR TWO_DAYS/ONE_MIN/outside_rth=true after the
freeze: CALL ID 929933691 (1,526 bars), PUT ID 929933999 (1,454 bars), expiry
2026-10-20. Input SHA256 values and outputs are retained with the raw arrays.
Contracts share market dates and exposure: these event counts are correlated,
not independent trials or a chronological unseen-session test. The replication
failed, and the candidate is **not installed in the runtime classifier**.
No thresholds were changed after seeing this replication.

```bash
python research_premium_search.py --inputs artifacts/premium_radar/call_history.json artifacts/premium_radar/put_history.json --output /tmp/frozen.json
python research_premium_search.py --frozen artifacts/premium_radar/development_frozen.json --inputs artifacts/premium_radar/replication_call.json artifacts/premium_radar/replication_put.json --output /tmp/replication.json
```

### Preserve future evidence

When the independently authorized IBKR worker runs, each completed source bar
is now archived under `.hunter-state/premium_bars/<contract-id>-<UTC-date>.jsonl`.
Set `IBKR_MCP_REPORT` to a location on persistent storage if the host otherwise
loses local files on restart/deploy. The archive requires a single writer.
Historical fetches retain actual receipt times; those times do not pretend to
be original market publication times. Repeated unchanged bars are deduplicated;
changed bar versions are appended without replacing the earlier observation.
Unfinished bars are excluded. Corrupt archives fail rather than silently reset.
Only allowlisted contract identity and market fields are retained; OAuth and
account responses are excluded. `premium_bar_versions_recorded` is exposed in
health metadata. This implementation does not assert that independent server
authorization or deployment has already happened.

Use the first version available at each prospective decision time when building
future chronological validation; never substitute later revised bars. Preserve
negative results. The new archive is evidence collection, not a prediction edge.
The project remains NOT READY for reliable early explosion alerts.

## Prospective shadow outcomes

The opt-in IBKR worker now reconciles `premium_shadow.jsonl` against the archived
first-received bar versions and appends terminal results to
`premium_outcomes.jsonl`. Each WATCH/ACCELERATION observation uses its actual
`detected_at`; earlier or partially elapsed detection-minute bars cannot count
as later outcomes. The horizon is the next five **full** minutes, so a detection
at 14:00:30 UTC is graded on 14:01–14:06 UTC, not on the already partly observed
14:00 candle. This differs from the historical event audit's anchor protocol and
must not be pooled with that audit or described as a lead-time test.

For complete, valid, positive-volume REALTIME source bars received within 120
seconds of bar completion, the outcome records the maximum trade-price rise,
maximum fall, final trade-price change and whether a +25% trade high was reached.
It does not assert an executable entry or exit, profit, probability, or that the
original movement had not already started. Missing data remain pending until
window end plus 120 seconds, then are censored with a reason. Frozen/delayed,
invalid, prematurely received or late historical bars are censored. Later bar
revisions never upgrade a result. A historical bulk download cannot pretend to
have arrived in time for an earlier signal.

Outcomes survive worker restarts without duplicate IDs, and corruption raises
an observable worker error. The health endpoint exposes only cumulative scored,
censored, pending and target-hit counts; pending/censored observations do not
become automatic losses or successes. This is evidence infrastructure; no new
positive live performance result or successful server deployment is claimed.

Worker polling now uses a start-to-start interval instead of adding a full
60-second wait after each network collection. A 25-second collection therefore
leaves 35 seconds until the next cycle. An overrun leaves a minimum one-second
pause; cycles do not overlap or issue catch-up bursts. This removes avoidable
local polling delay but cannot guarantee source latency or free-host uptime.
