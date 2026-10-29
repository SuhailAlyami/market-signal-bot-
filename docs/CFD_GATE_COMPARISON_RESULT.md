# CFD final-gate comparison result — 2026-10-29

**NOT_READY. No subscription, order or external alert activated.**

Protocol fixed at commit 549ee0ef57093abce8b6547369127ef7038a41d6 before reading results. Source: tradingview/Suhail_Hunter_CFD_COMPARISON.pine. Actual Pine compilation and table rendering observed on signed-in TradingView, CAPITALCOM:SPX500 standard 1 minute. Fixed development date: 28 October 2026, midnight-to-midnight KSA. UI coverage: Oct19 01:00 through Oct29 10:51 KSA. This is a consumed-date matched-confirmation ablation, not independent/forward validation and not a rerun of each policy's own lifecycle.

Official statement time verified: Oct28 14:00 New York = 21:00 Riyadh. Conference21:30. No news-value or direction assumption used.
https://www.federalreserve.gov/newsevents/2026-october.htm
https://www.federalreserve.gov/monetarypolicy/fomcpresconf20261028.htm

Positive/negative/flat means signed next-bar Open to fifth future consecutive-minute Close; underlying CFD points only. No fills, costs or profitability claimed. UP points is the always-UP return at identical sample timestamps; it is not a full-market detector baseline.

| Policy | Part | Outcomes | Positive | Negative | Flat | Censored | Signed CFD points | Always-UP points |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ORIGINAL | PRE | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ORIGINAL | CROSS | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| ORIGINAL | POST | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_TICK | PRE | 2 | 1 | 1 | 0 | 0 | -0.4 | -0.4 |
| NO_TICK | CROSS | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_TICK | POST | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_BODY | PRE | 3 | 1 | 2 | 0 | 0 | -1.0 | 1.0 |
| NO_BODY | CROSS | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_BODY | POST | 1 | 1 | 0 | 0 | 0 | 0.2 | -0.2 |
| NO_RISK_CAP | PRE | 1 | 0 | 1 | 0 | 0 | -1.5 | -1.5 |
| NO_RISK_CAP | CROSS | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_RISK_CAP | POST | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| THREE_RELAXED | PRE | 9 | 2 | 7 | 0 | 0 | -9.6 | 1.4 |
| THREE_RELAXED | CROSS | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| THREE_RELAXED | POST | 1 | 1 | 0 | 0 | 0 | 0.2 | -0.2 |

Totals: NO_TICK1+/1- (-0.4 points); NO_BODY2+/2- (-0.8); NO_RISK_CAP0+/1- (-1.5); THREE_RELAXED3+/7- (-9.4), versus +1.2 always-UP points on its same ten timestamps. ORIGINAL remains empty, so no success-rate comparison with it is meaningful. These point totals are diagnostic sums, not a tradable portfolio or option P&L.

Conclusion: relaxing final gates increases eligible observations but supplies no positive directional evidence on this date. FOMC partition is highly imbalanced (nine confirmations pre-release, one post-release); no post-FOMC advantage can be inferred from one +0.2 point observation. Do not choose the single post-event winner or retune thresholds on these results. All variants and negatives retained; no winning production variant selected.

Limits: no raw export for independent replay; no completed independent-day replication; no early-explosion event precision/recall or lead-time estimate; no causal prefix test of the diagnostic itself. Script reload resets realtime provenance. Free unsaved editor/chart state does not establish permanent mobile installation or server alerts. Keep NOT_READY and no paid-upgrade recommendation.

Next research step: test a separately fixed early-setup hypothesis with independently defined movement labels and an untouched chronological date, rather than promoting these final-gate relaxations. Such future work has not been run by this report.
