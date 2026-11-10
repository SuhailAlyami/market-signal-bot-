# Suhail Hunter — conservative explosion watch (pilot)

This adds an **opt-in** 5-minute SPY/QQQ breakout watcher without changing the current bot. It uses Yahoo Finance bars, which can be delayed, incomplete, unavailable or revised. **It is not tick-by-tick monitoring or options flow.** No SPX 0DTE contract recommendations or order execution are made.

## Setup
1. Merge this PR only after reviewing and testing.
2. In GitHub Actions secrets, configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Never put credentials in source files.
3. Enable the repository GitHub Actions workflow named **Suhail Explosion Watch**, then run it via `workflow_dispatch` to validate connectivity. Outside NYSE session, it deliberately sends no alert.
4. The schedule is every 5 minutes during a broad UTC window. NYSE calendar gates signals for holidays/early closes; scheduled jobs can be delayed or skipped due to platform limits. Scheduled triggers need the workflow on the default branch.

## Signal rules
Uses **completed** 5-minute candles only. The alert path is the original confirmation unless `EXPLOSION_MODE=early`: a close beyond the prior range (default 30 bars), relative volume at least `EXPLOSION_LEGACY_RVOL_MIN` (2), a five-bar move of at least `EXPLOSION_LEGACY_MOMENTUM_PCT` (0.35), and a distance of at least `EXPLOSION_LEGACY_MIN_DISTANCE_ATR` (0.1) times ATR. A delayed bar (default >12 minutes) is rejected. Alerts still require the NYSE cash session.

`EXPLOSION_MODE=early` switches to a short-range release measured in prior ATR (`EXPLOSION_LOOKBACK`, `EXPLOSION_RVOL_MIN`, `EXPLOSION_EXT_MIN_ATR`, `EXPLOSION_EXT_MAX_ATR`, `EXPLOSION_BODY_MIN_ATR`, `EXPLOSION_COOLDOWN_BARS`). That mode was measured and **not promoted**: on the held-out sessions it missed most explosions and did not improve entry quality. See `artifacts/explosion_early/report.json`.

`EXPLOSION_MODE=context` is the one-minute study (opening drive, VWAP, lagged VIX/VIX1D, macro clock, lagged NYSE composite). It does not send Telegram alerts. The isolated-test verdict is in `artifacts/explosion_1m/report.json`. The strength score is a deterministic heuristic and **not** a calibrated probability or trading recommendation.

## Constraints and follow-up
- Alert deduplication is fail-closed: private GitHub Issues store the last signal key for each symbol. The workflow requires `issues: write` and the workflow-provided `GITHUB_TOKEN`. Concurrency control serializes regular scanner runs. This suppresses duplicate alert messages for the same candle in normal operation, but issue API failures disable alerts, and a failure after reserving can lose an alert. It is not exactly-once delivery.
- This requires market-data-source validation and historical out-of-sample testing before any trading use.
- Existing `auto_auditor.py` can overwrite source code using unchecked LLM outputs. Do not run it against production; its duplicate workflow files are incorrectly nested and do not constitute dependable automated testing.
- No secrets are read or exposed by this change; existing workflows are untouched.
- Run tests: `python -m unittest discover -s tests -v` (requires pandas and the dependencies from the workflow).
