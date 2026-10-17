# Suhail Hunter — conservative explosion watch (pilot)

This adds an **opt-in** 5-minute SPY/QQQ breakout watcher without changing the current bot. It uses Yahoo Finance bars, which can be delayed, incomplete, unavailable or revised. **It is not tick-by-tick monitoring or options flow.** No SPX 0DTE contract recommendations or order execution are made.

## Setup
1. Merge this PR only after reviewing and testing.
2. In GitHub Actions secrets, configure `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. Never put credentials in source files.
3. Enable the repository GitHub Actions workflow named **Suhail Explosion Watch**, then run it via `workflow_dispatch` to validate connectivity. Outside NYSE session, it deliberately sends no alert.
4. The schedule is every 5 minutes during a broad UTC window. NYSE calendar gates signals for holidays/early closes; scheduled jobs can be delayed or skipped due to platform limits. Scheduled triggers need the workflow on the default branch.

## Signal rules
Uses **completed** 5-minute OHLCV candles: 30-bar prior range breakout, relative volume >=2, momentum over five bars >=0.35%, and distance >=0.1 ATR. The strength score is a deterministic heuristic and **not** a calibrated probability or trading recommendation. Each message includes source and bar-close timestamp. A delayed bar (>12 minutes) is rejected.

## Constraints and follow-up
- Alerts may repeat if GitHub Actions reruns the same completed bar. Durable deduplication requires persistent state and is not implemented.
- This requires market-data-source validation and historical out-of-sample testing before any trading use.
- Existing `auto_auditor.py` can overwrite source code using unchecked LLM outputs. Do not run it against production; its duplicate workflow files are incorrectly nested and do not constitute dependable automated testing.
- No secrets are read or exposed by this change; existing workflows are untouched.
- Run tests: `python -m unittest discover -s tests -v` (requires pandas and the dependencies from the workflow).
