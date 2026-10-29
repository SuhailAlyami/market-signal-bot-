# CFD visual diagnostic result — 2026-10-29

Status: NOT_READY. No subscription or external alert created.

Protocol fixed before outcome code: commit 7358ef5cb33726cee818216c2d03466ab235d076, docs/CFD_DIAGNOSTIC_PROTOCOL.md. Platform: signed-in TradingView Pine Editor, CAPITALCOM:SPX500 standard 1-minute candles. Pine compiled and the diagnostic table rendered in the chart. No API retrieval, data export or fabricated prices.

The chart reported loaded coverage from 2026-10-19 01:00 to 2026-10-29 10:40 Asia/Riyadh. The fixed scored historical window was ONLY 2026-10-28 00:00 to 2026-10-29 00:00 Asia/Riyadh, end exclusive. Counts read from the rendered table:

| Stage | Count |
|---|---:|
| Candidate bars | 19 |
| SETUP transitions | 17 |
| Confirmation transitions | 10 |
| Eligible completed plans | 0 |

No qualified five-minute outcomes were available: positive 0, negative 0, flat 0, pending 0. This is an empty eligible sample, NOT 0% success and NOT 100% safety. Live-instance eligible signals/outcomes also zero at capture; this does not establish continuous monitoring or forward validation.

Overlapping final rejection counters: insufficient relative broker tick activity 4; trend 0; confirmation candle body opposing direction or zero 5; risk distance outside [mintick, 2 ATR] 4; invalid stop placement 0. Counts overlap and must not be summed as unique signals. No threshold or gate was relaxed based on these results.

Observed bottleneck: setups and confirmations occur but all confirmed scenarios are filtered by one or more final plan gates on this consumed CFD date. This finding is descriptive; it does not prove that removing any gate improves precision, recall, lead time or profitability. Original SPX/ES historical annotations visible from an older chart indicator are not results of this CFD diagnostic.

Limits: broker tick counts are not exchange volume; CFD points are not SPX cash/option prices. There is no retained raw OHLC export for independent replay and no causal prefix/future-poison audit of this new Pine diagnostic yet. Future code reloads reset live provenance; free browser chart activity is not an always-on saved server alert. Account plan blocked script saving and technical alerts. Source and protocol are retained in this branch, but permanent mobile availability is unverified. No subscription recommendation is justified by this result.
