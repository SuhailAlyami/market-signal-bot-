# Detector research v2 — measured comparison, 20 October 2026

**Decision: NOT READY. No new detector is installed in runtime. Notifications
remain off. No option execution or profit has been demonstrated.**

This work changes the detector research itself: local premium breakouts,
ES/NQ confirmation, a regularized multinomial model, and a bounded nonlinear
histogram-boosting comparator. It also fixes an evaluation defect. Software
regression success is reported separately from market quality.

## Why the previous detector missed moves

The 7690 option pilot contains strong turns well below the previous 20-minute
premium high. A rule requiring that high to break can identify the move late.
Some nearby-strike moves have flat or inactive trade bars before a jump; there
is little usable precursor evidence in those prints. A historical last-trade
high does not establish that an executable bid/ask opportunity existed.

The new local hypothesis uses the previous 3/5-minute high, relative volume,
positive one/three-minute returns and a close in the upper 40% of its current
bar. Eight bounded settings were compared on 7690 development inputs. The best
two by train timely F1 were checked on the already inspected 7695 validation
inputs. Selection required at least three scored train signals. These are
related contracts on shared dates, not independent train/validation sessions.
The chosen lookback=5, relative-volume=2.5, minimum one-minute return=1.5% was
committed in `7fd898425e71adc9af38528bf41b298e23a9ac06` BEFORE retrieving the
four additional 7685/7700 CALL/PUT histories. The original frozen artifact is
retained; settings were not changed after replication.

### Separate-contract option replication

The exact same +25% within five future trade-minute bars event protocol was
used. The four additional contracts expire on 20 October 2026. Histories were
trimmed to the predeclared common cutoff, 20 October 04:41 UTC, so later
retrieval time could not expand the test interval. Source arrays and hashes
are retained. The sample mixes days to expiration and must not be described
as historical 0DTE-only testing.

| Method | Scored signals | Events matched | Before onset | Within first minute or before | False alarms |
| --- | ---: | ---: | ---: | ---: | ---: |
| New local, zero added delay | 14 | 2 of 4 | 0 | 1 | 12 |
| New local, +60 seconds | 14 | 2 of 4 | 0 | 0 | 12 |
| Previous acceleration, +60 seconds | 9 | 0 of 4 | 0 | 0 | 9 |
| Basic breakout, +60 seconds | 21 | 1 of 4 | 1 | 1 | 20 |

The local candidate fails replication. It is not promoted. More detections
with twelve false alarms are not reliable early opportunity identification.
The zero-delay first-minute match disappears with only 30 seconds added delay.

### Evaluation defect and transparent correction

The old premium evaluator matched `event.anchor <= delivered_time`. Increasing
latency could move a signal generated BEFORE the event anchor into its window,
creating extra matches solely because delivery was slower. Matching now requires
`event.anchor <= generated_time` and `delivered_time <= target_minute_start`.
Delay cannot create eligibility by moving the same generated signal across the
anchor. A synthetic regression covers this failure in both premium evaluators.

This defect was discovered AFTER reading the replication output. The original
output is retained as superseded (`local_replication.json.gz`), along with an
explicit amendment and the corrected re-analysis. The original candidate
settings are unchanged, but the corrected re-analysis is **not called an
untouched test**. Zero-delay matching is unchanged. Previous negative outcomes
are not replaced by a claimed success.

## Four-week underlying comparison

ES and NQ minute data are the existing retained Yahoo snapshots under
`artifacts/issue16/data/`: 20 regular sessions, 10 earlier train, 5 validation,
and the last 5 chronological test sessions (12–16 October 2026). This dataset
was already studied before this experiment. The test dates are reused
retrospective evidence, NOT a new independent untouched holdout.

The existing causal harness retains completed-minute features, exact-time
cross-market joins, training-only normalization, horizon embargo, walk-forward
training folds, validation selection, one-to-one directional event matching,
Wilson intervals and session-block bootstrap. No prices are filled across
missing counterpart minutes. Events remain the predeclared first +/-
max(0.06% of price, two prior ATR) move within ten minutes; these underlying
moves do not imply +25% SPX option returns.

- Rules: 16 settings per symbol across local range release, synchronized ES/NQ
  local release, synchronized pre-level contraction, and breakout/retest hold.
- Linear model: 16 causal inputs, three L2 strengths, two expanding train folds;
  top two strengths receive three validation thresholds. Scaling and class
  weighting use train only. Scores are not calibrated trading probabilities.
- Nonlinear model: the same targets/splits/selection with 100 boosting rounds,
  seven leaves, minimum 80 samples per leaf, fixed seed and three L2 strengths.
  Early stopping is disabled so it cannot silently draw validation rows from
  the chronological training set. No test results choose a threshold or refit.

All families are published, including failures. The following metrics assume
zero added availability delay; full reports also stress 1/2/5/10 minutes.

| Symbol / method | Signals | Matched events | Early matches | False/session | Median lead |
| --- | ---: | ---: | ---: | ---: | ---: |
| ES basic breakout | 66 | 18 / 121 | 3 | 9.6 | 0 min |
| ES selected rule (retest) | 23 | 6 / 121 | 1 | 3.4 | -1 min |
| ES linear | 172 | 19 / 121 | 15 | 30.6 | +2 min |
| ES nonlinear | 165 | 23 / 121 | 18 | 28.4 | +2 min |
| NQ basic breakout | 74 | 25 / 143 | 4 | 9.8 | -1 min |
| NQ selected cross-market pre-level | 16 | 8 / 143 | 4 | 1.6 | +0.5 min |
| NQ linear | 159 | 29 / 143 | 21 | 26.0 | +1 min |
| NQ nonlinear | 118 | 22 / 143 | 18 | 19.2 | +2 min |

NQ cross-market pre-level has 50% matched-event precision but only 25% EARLY
precision and 4/143 early-event recall. It reduces noise relative to the simple
breakout while missing most events. One extra minute of delay leaves two early
matches; at ten minutes none remain. The ES learned models generate roughly
28–31 false alarms per session. No model dominates all baselines and all
objectives, and NQ results do not validate an SPX 0DTE detector.

The full reports include Wilson and bootstrap intervals. Only five reused test
sessions and 16 NQ rule signals make the apparent precision imprecise; events
and sessions may remain correlated. No statistical-significance or profit claim
is made. The research candidates remain isolated from live recommendation code.

## Reproduce

```bash
pip install -r requirements.txt -r requirements-research.txt
python hunter_crossmarket_research.py --es artifacts/issue16/data/es_1m.csv.gz --nq artifacts/issue16/data/nq_1m.csv.gz --output /tmp/cross --as-of 2026-10-19T09:00:51+00:00
OPENBLAS_NUM_THREADS=1 python hunter_linear_research.py --es artifacts/issue16/data/es_1m.csv.gz --nq artifacts/issue16/data/nq_1m.csv.gz --output /tmp/linear --as-of 2026-10-19T09:00:51+00:00
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python hunter_boosted_research.py --es artifacts/issue16/data/es_1m.csv.gz --nq artifacts/issue16/data/nq_1m.csv.gz --output /tmp/boosted --as-of 2026-10-19T09:00:51+00:00
```

Full JSON reports and new option source arrays are gzip-compressed under
`artifacts/detector_v2/`; `summary.json` is readable without decompression.
The manifest gives uncompressed and gzip SHA256 hashes. Read a report with:

```python
import gzip, json
with gzip.open('artifacts/detector_v2/boosted_v2_es_report.json.gz', 'rt') as f:
    report = json.load(f)
```

To repeat the corrected option replication, decompress the amended freeze and
four local source arrays, then run `run_premium_local.py --frozen ... --inputs
... --output ...`. It verifies the corrected source code hash and rejects
reuse of development input hashes. The amendment identifies the original freeze
commit. `premium_local_research.develop()` reproduces development search; after
the evaluator correction its rankings can differ, so it must not overwrite the
historical pre-replication freeze or silently choose a new candidate on this test.

## What remains necessary

A reliable SPX 0DTE version requires independent future sessions with directly
observed option books/trades and receipt times, then a frozen evaluation that
beats baselines without unacceptable false alarms. Repeatedly selecting on these
same dates cannot supply that evidence. This work establishes useful comparisons
and fixes a scoring defect; it does not establish the product acceptance criteria.
