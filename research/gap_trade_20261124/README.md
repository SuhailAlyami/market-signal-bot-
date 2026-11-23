# Gap continuation trade — 2026-11-24 — verdict: INCONCLUSIVE / UNPROVEN

Rule: if SPX opens at least 0.5 m beyond the previous close (m = prev_close x VIX/100/sqrt(252)), trade in the
gap direction at the open and exit at the close. Cost 1 SPX point per round trip.

| Test | n | Win | Avg pt/trade | 95% CI |
|---|---|---|---|---|
| Train 2010-2019 (threshold chosen here) | 114 | 64.0% | +4.6 | +0.4..+8.8 |
| **Test 2020-01..2026-11-13, SPX index daily** | 274 | 59.1% | **+8.7** | +2.5..+14.9 |
| Same days, random direction (p95) | — | — | +4.2 | — |
| Same days, always long | 274 | 50.0% | −5.7 | — |
| 2024-2026, SPX hourly, entry at open | 141 | 54.6% | +1.9 | −6.8..+10.6 |
| **2024-2026, SPY (tradable), entry at open** | 179 | 52.0% | **−2.2** | −9.9..+5.5 |
| 2024-2026, SPX entry at 10:30 | 141 | 52.5% | −4.2 | −11.8..+3.4 |
| 0DTE ATM call/put held to close (model, premium 0.4 m) | 274 | 36.9% | −2.4 | −6.3..+1.5 |

Reading: the index result is significant, but it does not survive on the tradable ETF or after the opening print
settles. Most of it is the SPX opening-print artifact: at 09:30 many stocks have not traded yet, so the index
open lags the real gap. Not a proven edge. It is shown in the daily message as a conditional plan with this
label, and scored live every evening (`evaluate_range.score_trade`), which gives the forward record.

Data: `GSPC_1d.json.gz` and `VIX_1d.json.gz` from branch `research/volatility-premium-20261115`; hourly files from
`data/history-20261114`. Run from a folder holding both clones (paths are in the scripts).
