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
