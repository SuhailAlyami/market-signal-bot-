# Codex mission: Suhail Hunter

You are the autonomous engineering agent responsible for finishing this repository, not just making tests green. Work on a branch, open a PR, and report measured outcomes. Avoid asking the owner to manually debug routine issues.

## Product goal
Find actionable *early* SPX 0DTE CALL/PUT opportunities before option premiums inflate. Identify potential ES/NQ or SPX directional expansion *before* or at the first reliable sign of acceleration. Deliver concise Arabic states: استعداد / دخول مشروط / إلغاء / خروج. **Never invent SPX option bid/ask, strike, expiration, fills or live-feed status.** Without a verified real-time option chain, emit research-only underlying WATCH, not executable option advice.

## Critical known defects
- A Render deployment being live and GitHub CI being green do not demonstrate market detection quality.
- The current `early_globex_watch.py` is based on 5m completed Yahoo futures candles, potentially delayed, and is not truly pre-breakout.
- `research_early_signals.py` 1m ES/NQ pilot (2026-10-19 GitHub Actions run 39222971595) was weak: ES pre-level 51.97%, impulse 50.72%, breakout 48.73% directional hits after 5m; NQ pre-level 53.97%, impulse 51.02%, breakout 46.94%. Do not claim an edge.
- Render free may sleep; GitHub schedule is best effort. `globex_render_worker.py` has default 2/day notification cap, which must never be mistaken for a detector limit. Evaluate all candidates and throttle only outbound alerts.
- Existing code contains several independent scanners; audit duplication, market hours/DST, bar freshness, incomplete candles, zero-volume bars, API errors and inconsistent scoring.
- The existing `backtest_explosion.py` is SPY/QQQ underlying research, not SPX option P&L.

## Engineering plan
1. Inventory all scanners, data sources, schedulers, tests, and signal outputs. Document a single event schema and separate detection from notification.
2. Build a reproducible event-based research harness with timezone-aware 1m OHLCV, **walk-forward chronological train/validation/test splits**, no future leakage, embargo for overlapping horizons, commissions/spread/slippage assumptions where applicable, and explicit data availability/latency checks. Preserve raw metrics/artifacts and negative results.
3. Benchmark pre-breakout setups: level proximity (prior day/session high-low, opening range), volatility contraction/expansion, acceleration, failed breakouts, multi-timeframe trend, relative volume, and no-signal baseline. Use parameter searches ONLY on training, select on validation, publish untouched holdout metrics. Measure event precision/recall, lead time vs movement onset, false alarms per session, and missed events—not only directional hit rate.
4. Separate `SETUP` (probabilistic early warning) from `TRIGGER` (confirmed), `INVALIDATION`, and `EXIT`. Implement hysteresis, cooldown, dedupe, stale-data fail-closed, and state persistence across Render restarts. Do not make claims of prediction certainty.
5. Explore lawful no-cost/low-cost *genuinely timely* market data options. Compare timestamps and latency empirically. Never describe delayed Yahoo bars as real time. Do not scrape paywalled data or bypass provider limits.
6. Integrate best **out-of-sample verified** detector into one runtime; keep alerts OFF for experimental variants. Keep low-noise Arabic Telegram alerts with evidence (symbol, bar timestamp, source, level, invalidation, confidence calibration, latency).
7. Only enable specific SPX 0DTE strike/premium suggestions when a legitimately sourced verified live options chain is available; otherwise no fabricated option quotes or trades.
8. Add CI regression tests for leakage, timezone/DST, stale feeds, opening minutes, alert state transitions, no duplicate sends, provider failures, and deterministic research fixtures. Verify deploy health separately from signal quality.

## Acceptance criteria
- Published reproducible out-of-sample test report including sample dates, event definition, baseline, precision/recall, median lead time, false alarms, misses, confidence intervals, and data limitations.
- No silent market-data outages: observable heartbeat and last completed bar timestamp.
- Live paper-trading/shadow log with detection timestamp, decision and later outcome, **no automatic real-money orders**.
- Evidence of measured improvement over baseline on untouched holdout, or explicitly mark NOT READY and continue research without false promises.
- Deploy/CI green and no regressions, but these are necessary, NOT sufficient.
- No new paid services or subscriptions without explicit owner consent. Favor existing GitHub/Render free resources, rate-limit requests and minimize compute.
- Work independently through implementation, tests, review, fixes and PR. Do not claim finished until acceptance criteria are evidenced.
