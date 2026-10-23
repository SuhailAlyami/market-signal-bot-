# Missed SPX rebound: 2026-10-23

Owner screenshot documents a rebound from the labelled wick 7612.07 to displayed 7650.76 (38.69 points). Screenshot alone does not establish precise candle times or a tradeable strategy edge. Actual original reader events below establish a late setup and a rejected confirmation, not an unavailable feed.

All times UTC (Riyadh = UTC+3):
- First recorded live observation in this interval: 14:34, close 7623.55.
- Lowest recorded CLOSE: 14:35, 7621.45. This differs from the chart wick 7612.07.
- SETUP: 14:48:00.784692, price 7646.03, level 7646.54: already 24.58 points above that recorded close, 13 minutes later.
- TRIGGER: 14:50:01.857912, 7647.28, reason `two_buffered_closes`.
- 14:50:02.050913: `signal_blocked`, reason `confirmation_filters_failed`.
- Subsequent recorded close 14:56: 7654.92.

## Proven causes and limits

The running SPX adapter uses native SPX OHLC, lagged ES volume, and ES trend confirmation. `strategy_rules.candidate` requires proximity to the preceding rolling-20 extreme, relative volume, and continuing trend. This is a continuation-near-level hypothesis; it cannot be described as an early reversal detector. Runtime then requires two buffered closes. The concrete setup happened after much of this rebound; processing delay at setup was only 0.785 seconds, so the minutes of lateness are not explained by callback processing.

The trigger passed the adapter's separate ES confirmation check and was rejected by `es_signal_plan.complete_plan`'s combined confirmation condition (ATR/price validity, relative volume, trend5, trend15, move). Existing journal stores only the combined reason. Which individual component failed is NOT established by the retained journal; do not invent this diagnosis or blame missing option quotes. Options are only examined after a successful complete_plan in this path.

Events explicitly say NOT_READY, analysis_only and notify_eligible=false. Previous shorthand that the window contained only NO_TRANSITION was incomplete: there are actual SETUP/TRIGGER records, retained in evidence.json. Infrastructure continuity is not detector quality. This is a failure against the owner's early-warning objective.

## Safe next work

Use this case only as development. Its backfilled OHLC may reconstruct price context but cannot stand in for original first-availability timestamps or missing historical ES feature values. Add individual confirmation-rejection diagnostics before assigning a specific cause; diagnose missed reversal readiness separately from continuation confirmation. No threshold relaxation, notification bypass, candidate promotion or repeated old validation is justified by one chart. Independent replication plus prospective shadow proof remain required. Current studies remain NOT_READY; no Pine parity success is claimed.

Original reader, alert configuration, Gateway and prospective recorder were left running unchanged. No orders, test notification, subscription or extra market-history request. This forensic evidence review is not a new strategy experiment.
