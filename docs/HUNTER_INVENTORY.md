# Suhail Hunter inventory and audit — Issue #16

Audit date: 2026-10-19 UTC. Product readiness: **NOT READY** until independent,
untouched out-of-sample evidence supports early detection and timely feed access
is verified. Software regressions, historical download success, HTTP uptime,
Telegram acceptance, and predictive quality are separate observations.

## Scanners, inputs, schedules, and outputs

| Component | Data and decision | Scheduler / persistence | Output and limits |
| --- | --- | --- | --- |
| `hunter_runtime.py` | Experimental ES/NQ completed 1m `pre_level` underlying detector using the shared causal features; validates feed before decisions | One runtime used by cloud/Render adapters; local state and append-only shadow journal | SETUP / TRIGGER / INVALIDATION / EXIT, heartbeat and later underlying outcomes; alerts OFF, no verified edge |
| `globex_render_worker.py` | Adapter for the shared runtime; Yahoo futures proxy | Render process poll; scans continue regardless of notification cap or Telegram credentials | Research shadow events and heartbeat; `get_status()` for HTTP diagnostics |
| `early_globex_watch.py` | Legacy 5m ES/NQ recent-range close breakout with RVOL >= 1.5 | Hand-coded US Eastern Globex weekly gate, not a complete CME holiday calendar | WATCH_UP / WATCH_DOWN; already completed breakout, not demonstrated pre-breakout detection |
| `asia_watch.py` | Archived 15m ES/NQ opening-hour range breakout, RVOL >= 1.5 | Manual legacy entry point only; Tokyo weekday / New York DST conversion; in-memory notification dedupe | Arabic research WATCH implementation retained for comparison; not launched by main |
| `explosion_detector.py` | Legacy SPY/QQQ Yahoo 5m, 30-bar range breakout, RVOL >= 2, momentum >= 0.35%, distance >= 0.1 ATR | NYSE exchange calendar handles holidays, early closes, DST | BULLISH / BEARISH WATCH; technical score is explicitly not success probability |
| `us_watch.py` | Calls legacy SPY/QQQ detector | Manual legacy entry point only; in-memory candle dedupe | Arabic Telegram research WATCH implementation retained for comparison; not launched by main |
| `cloud_scan.py` | GitHub Actions adapter for the same `HunterRuntime`; no independent scanner | Every 5m, best effort; GitHub schedule can lag/drop; serialized runs and best-effort state cache | Shadow journal and heartbeat artifacts; no GitHub issue or Telegram notification |
| `market_signal_bot.py` | Hosts Flask and the canonical shadow worker; retains legacy FVG / order-block / RVOL / RSI / momentum code for comparison | Render main process; independent legacy workers and monitor are not launched | `/`, `/health`, research status; legacy SQLite adaptive state is not evidence of prediction quality |
| `ibkr_readiness.py` | Optional operator-controlled loopback socket probe; contract metadata only | On demand; disabled by default | Open socket is not IBKR authentication, entitlements, live quote, or option-chain verification |
| `backtest_explosion.py` | Legacy SPY/QQQ 5m forward underlying move, exact legacy detector | On demand and historical smoke CI | Exploratory in-sample underlying result; no split/embargo and no option P&L |
| `research_early_signals.py` | Legacy exploratory 1m ES/NQ pre-level, impulse, breakout comparison | On demand / manual research workflow | Directional hit rate; overlapping windows; explicitly not out-of-sample evidence |
| `hunter_research.py` | Event-based chronological train/validation/test research | Offline, archived input and deterministic fixtures | Selection on train/validation; untouched holdout, baselines, event metrics and limitations |
| `acquire_hunter_data.py` | Bounded normal Yahoo 1m history requests and completed-bar-age observations | On demand, up to four recent 7-day chunks per symbol; no retry/fallback prices | Archived UTC OHLCV snapshots, request durations, errors and SHA-256 manifests; no publication-latency claim |

The runtime/research additions are described by their implementation and report;
legacy entry points remain in the repository to preserve previous experiments.
No independent legacy score should be interpreted as a calibrated probability.

## Event contract and state

New runtime events share `schema_version=1`. A stable hashed signal identity binds
symbol, state, scenario start, and completed bar timestamp. Records include UTC bar start/end and
actual detection time; Yahoo is always marked potentially delayed with
`live_feed_verified=false`. Price and level refer to the underlying. There is no
SPX strike, expiry, option bid/ask, executable fill, or automatic order.

| Field family | Meaning |
| --- | --- |
| Identity | `event_id`, `symbol`, `detector`, `schema_version`, `record_type=event`, `state`, `state_ar`, `direction` |
| Time | UTC `bar_start`, `bar_end`, `detected_at`, `detection_delay_seconds` |
| Decision | Underlying `price`, `level`, `invalidation`, `rvol`, `reason` |
| Confidence | `confidence_status=uncalibrated`, `confidence_probability=null`; never an invented probability |
| Source/readiness | `source`, `analysis_only=true`, `live_feed_verified=false`, `readiness=NOT_READY`, `notify_eligible=false` |
| Lifecycle | SETUP = استعداد; TRIGGER = دخول مشروط (research underlying only); INVALIDATION = إلغاء; EXIT = خروج |

A SETUP is probabilistic and may fail. A TRIGGER follows a completed-bar condition;
it is not a verified executable SPX option trade. State, cooldown and event IDs
prevent repeat transitions across process restarts when the same state file is
retained. Render's ordinary filesystem is ephemeral: local-file persistence
cannot promise dedupe across replacement/redeployment or across simultaneous
instances. The default backend is reported as non-durable, and alerts stay OFF.
No durable paid service has been requested or provisioned.

Detection and logging run independently of notification capacity. A daily alert
cap may throttle outbound messages only; it cannot stop candidate evaluation,
heartbeat, invalidation, exit, or later-outcome recording. Provider failures and
stale/incomplete/invalid bars must be visible in heartbeat rather than silently
becoming “no signal”. A freshness check measures observed completed-bar age, not
proof of exchange-to-provider latency or real-time entitlement.

HTTP diagnostics additionally expose heartbeat age and stalled-worker status.
Forward shadow outcomes start from the first complete minute after actual
detection, so they never credit a return before the decision arrived. The
reference Open is diagnostic and is not labeled an executable fill. Actual
retained live receipts were rejected as stale and produced no valid live setup
or resolved trade outcome; see [the measured report](ISSUE16_REPORT.md).

## Initial defects found

| Finding at baseline `357cdd5` | Consequence / handling |
| --- | --- |
| Globex `count < max_daily` wrapped `scan_once`; default cap 2/day | Detection stopped after two sends. Shared runtime must continue scanning and recording every candidate. |
| Three independent Render watchers enabled by default; EARLY and ASIA also scanned the same futures in cloud | Duplicated provider requests, inconsistent signals and repeated alerts. Main and cloud now use one experimental shadow runtime; independent legacy notification paths are not launched. |
| Render dedupe/cooldowns lived in Python sets/dicts | Process restart could resend. Persist transitions; disclose ephemeral-storage limit. |
| `/health` returned healthy from uptime alone | A sleeping/dead worker or stale feed looked healthy. Expose last heartbeat, per-symbol source/status and last completed bar separately from HTTP liveness. |
| Early Globex tests were top-level pytest functions while all CI used unittest | Five tests were silently undiscovered. Converted to `unittest.TestCase`; all five now execute under the common suite. |
| Asia CI omitted full application/calendar requirements | Dependency availability was accidental/mocks masked missing runtime imports. Both regression workflows now install `requirements.txt`. |
| Syntax checks enumerated only selected modules | New runtime/research modules could escape checks. Both regression workflows compile every root Python module and the tests. |
| Globex/Asia Telegram formatters contained literal `\\n` | Messages could display backslash-n text. Shared Arabic formatting uses actual line breaks. |
| Globex gate lacked holiday exceptions; legacy Asia validation lacked complete OHLC/gap checks | A weekly session gate alone is not a verified exchange calendar. Completed-bar validation and fail-closed freshness remain mandatory. |
| Legacy exploratory research reused overlapping samples and did no holdout selection | Hit rate cannot establish early detection edge. Preserve negative results and use the new event-based report. |
| Legacy CoinGecko fallback fabricated high/low from sampled prices and used naive local timestamps | These are not genuine OHLCV bars and cannot support this futures/options research. Legacy monitor is not launched and its data is outside the verified detector inputs. |
| GitHub issue dedupe used Search indexing or first 100 issues | Index lag/reruns and pagination can miss old keys; not exactly-once delivery. Experimental outbound alerts remain OFF. |

## CI and scheduling inventory

- `explosion_tests.yml`: full deterministic unittest regression and syntax checks;
  separate legacy SPY historical-availability smoke with archived research output.
- `asia_watch_tests.yml`: full regression using the same application dependencies.
- `early_research.yml`: manual/selected-main-change exploratory ES/NQ study,
  archived JSON; research output, not a correctness or profitability gate.
- `hunter_research.yml`: offline reproduction of all four retained studies with
  exact research dependencies; compares complete JSON reports against the
  archived measurements. Reproducibility does not establish a predictive edge.
- `explosion_watch.yml`: every-five-minute Actions schedule; best effort and
  serialized. This cannot guarantee the low latency required for SPX 0DTE.
- `monday_readiness_notice.yml`: manual or workflow-change-triggered Telegram
  preparation notice; no detection evidence. Do not trigger during verification.
- `notification_delivery_test.yml`: manual or workflow-change-triggered GitHub
  notification issue, not a market event. Do not trigger during verification.
- `.github/auto_audit.yml`: misplaced, inactive as a workflow; do not move/activate
  its unchecked source overwrite routine.

## Observed health, separately from predictive quality

**Code health at baseline.** GitHub reported successful main-commit regressions
for `357cdd57ebaa2794567dd033455a648897aa7c6c`:
[Asia watcher CI 39225951411](https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/39225951411)
and [Suhail Explosion Tests 39225951369](https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/39225951369).
These runs predate this PR and omitted the five Globex function-style tests.
The PR's own complete regression results must be reported separately.

**Deploy health.** Render MCP was reachable, but read-only `list_services({})`
returned `no workspace selected`; no deployment, current live commit, logs,
worker execution or market-feed freshness was verified through that connector.
The connector explicitly required owner confirmation before choosing a workspace.
No workspace was switched and no deploy, restart, configuration, or paid resource
was created. Existing hosted HTTP observations, if obtained separately, establish
only what that endpoint actually returns, not current code or prediction quality.

**Predictive quality.** The known earlier 1m pilot
[39222971595](https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/39222971595)
was weak: ES pre-level/impulse/breakout directional hits were 51.97% / 50.72% /
48.73%; NQ were 53.97% / 51.02% / 46.94%. This is exploratory and does not
establish an edge. Use the new reproducible report's event definition, split
boundaries, holdout metrics, confidence intervals and latency limitations to
assess the experimental detector. Passing tests does not improve these numbers.
