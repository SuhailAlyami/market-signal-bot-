# AI_CONTEXT — read this first (any AI tool: Claude, ChatGPT/Codex, Grok, Replit, ...)

Last updated 2026-11-15. Owner: SuhailAlyami. Language with the owner: Arabic, concise. Code/logs: English.

## Goal
Catch rare, high-quality SPX opportunities (originally: early SPX 0DTE CALL/PUT before premiums inflate). Status: **NOT_READY / RESEARCH_ONLY**. No automatic real-money orders. Never invent prices, option quotes, fills or test results.

## What is live on `main` (working, automated)
| Piece | Files | What it does |
|---|---|---|
| Pre-open range alert (Telegram) | `range_alert/daily_range.py`, `.github/workflows/range_alert.yml` | Expected daily move = prior close x VIX/100 / sqrt(252). Bands +/-1 (high and low both inside on 68.7% of days, 2010-2026) and +/-1.5 (90.1%). Options-cost line (VIX vs trailing 21-day realized vol). No direction call (base rate: 54.5% up days since 2010). Slots 13:13-16:13 Riyadh, Mon-Fri. |
| Post-close check (Telegram) | `range_alert/evaluate_range.py`, `.github/workflows/range_evaluate.yml` | Actual high/low/close vs the bands, live cumulative hit rate since 2026-11-16. Slots 00:37-04:37 Riyadh. |
| Data collector | `research/spx_collection/`, `.github/workflows/spx_collect.yml` | Yahoo SPX 1m (7d) + 5m bars for ^GSPC and 10 megacaps, stored on branch `data/spx-collection` (first read canonical, gaps never filled, raw kept). |
| Frozen forward test | `research/breadth_20261109/` | Breadth-agreement candidate (rejected as a rule in development). Runs only once >= 190 high-agreement events exist in sessions >= 2026-11-05; needs C1-C5 incl. net > 0 after 1-point cost. |
Secrets in Actions: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (and `GROQ_API_...`). Never print or request secret values.

## What was tested and FAILED (do not repeat without a genuinely new reason)
All on SPX/ES, preregistered protocols, costs included (36+ experiments):
- Intraday explosion/reversal detectors on 1m/5m/30s bars (wave, CUSUM, opening range breakout/reclaim, opening direction, ES lead, ES volume, VIX1D, structure waves): direction ~50%, signals arrive after ~37% of the move, net negative after a 1-point cost.
- Square of Nine (Gann) levels: -273.7 pts out of sample, worse than 95% of random-anchor levels.
- Buying short-dated options: lost in 93% of cycles in a 1990-2026 model test (option buyers pay the volatility risk premium).
- Pre-FOMC drift, unconditional turn-of-month: published effects faded after ~2015 (literature).
- Breadth agreement of top-10 stocks: difference +1.8 pt/trade in development but net ~0 after cost; frozen for forward test.

## What has real evidence
- **Volatility risk premium**: VIX > subsequent 21-day realized vol on 86% of days 1990-2026 (89% in 2023-2026). Buyers of options overpay on average. (`research/volatility_premium_20261115`)
- **Range forecasting** from VIX is well calibrated (68.7% / 90.1%), unlike direction.
- **Defined-risk put credit spread** (model-priced, no skew): mean +0.95 pt/cycle at 2-pt cost, 95% CI includes 0 -> INCONCLUSIVE; rare losses of 90-155 pts. (`research/put_spread_vrp_20261115`)

## Data access facts
- Yahoo chart API works (`query1/2.finance.yahoo.com`), delayed/undeclared latency. Options chain endpoint requires a crumb: do not bypass.
- IBKR connector (claude.ai) gives SPX option OI + model greeks per contract; data status was FROZEN_DELAYED on a weekend; one-pass coverage check protocol: `research/dealer_gamma_20261115/CHECK_PROTOCOL.md`.
- TradingView cannot be reached from cloud agent sessions; no webhook.

## Rules for any AI working here
1. Read this file, then `RESUME.md`, then open PRs/branches (newest first).
2. One change per experiment; commit `protocol.json` before computing; keep failures; never retune on test data.
3. Work on a branch; the owner merges to `main` unless they explicitly ask you to.
4. Report results in concise Arabic with numbers, sample size and the verdict (SUCCESS / FAILURE / INCONCLUSIVE).
