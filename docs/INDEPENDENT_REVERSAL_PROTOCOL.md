# Locked independent reversal test — specified before acquisition

The old comparison established an integration defect, not a fair stand-alone
reversal test: continuation trend filters rejected302/304 reversal triggers.
Neither the current detector nor an alternative is approved by the other's failure.
Both remain NOT_READY unless they satisfy independent, absolute quality criteria.

## One alternative, separate strategy rules, common safety

Baseline: existing hunter-rolling20-v2 continuation SETUP/two0.1ATR closes,
current volume/5/15minute trend/body confirmations,10minute expiry/5minute cooldown.
Replay existing lifecycle; verify cached features against production prefixes.

Alternative `amd-reclaim-cisd-v1`, PDFpages1–6 and145, one precise form:
prior20 completed-minute high/low range; previous5range/previous20range<=0.65
(existing development parameter, an operational accumulation proxy); current
completed candle strictly sweeps exactly one edge and closes strictly inside;
body points in reclaim direction; preceding candle has opposite body direction;
reclaim close also passes that preceding candle's OPEN in reclaim direction
(explicit one-candle delivery-shift form, not every discretionary CISD variant).
RVOL>=1.2 as before. Stop one ES tick beyond actual swept wick. No continuation
trend5/15 filters on reversals. No future swing pivots, HTF/SMT/POC inventions.
No parameter search or second alternative after results.

Common risk builder for BOTH models: finite positive prices/ATR, tick-aligned
close±0.05ATR entry zone, outward stop rounding, stop strictly beyond entry,
risk>=1tick and<=2ATR, targets1R/2R positive. Compare builder exactly with current
production complete_plan on continuation-eligible fixtures. Same completed-bar,
31contiguous-valid-minute warmup, session calendar, expiry and cooldown; gaps
cancel scenarios. Generate decisions BEFORE future outcome censoring.

Live transport quote freshness, authenticated relay, real option quotes, entry
zone recheck and per-channel durable dedupe remain unchanged and cannot be bypassed
by a model. Historical acquisition is not a live freshness/options entitlement test.
No production change until acceptance; the current reader is not restarted.

## Independent data and acquisition stop condition

Development data previously used:2026-09-21 through2026-10-18 ESproxy.
Locked test dates, NOT inspected by either prior rule-selection exercise:
2026-09-01,02,03,04,08,09,10,11,14,15 (10complete RTH sessions).
Resolve actual ES September2026 future on CME with includeExpired=True; retain
conId/localSymbol/expiry, raw trades OHLCV, errors, hash and request timestamps.
One separate read-only Gateway client; at most10 sequential1D/1minute TRADES
historical requests,useRTH=1, ending00:00UTC the next calendar day per date.
No orders/accounts, paid snapshots, subscriptions or repeated permission probes.
Stop on the first substantive acquisition error; record exact error and need.
No fallback to development bars, no inspecting another test period after outcomes.
Earlier dates are an independent disjoint-period test, not forward/live evidence.

Require all10 expected sessions to include09:30–15:59 America/New_York with valid
data; no filling or invented missing volume. Full-session completeness plus gaps/
warmup and horizon censoring reported. This remains underlying ES research, NOT
SPX or SPX options validation. Missing permissions/data cannot earn a pass.

## Metrics and acceptance fixed now

Same frozen independent-event scorer:10minute horizon, target max0.06%/2priorATR,
onset25% of target, no ambiguous paths, one-to-one direction matching. Embargo
10minutes on both ends of each session. Report all detections, censored counts,
precision, recall, EARLY precision/recall/F1, false alarms/session, misses, lead,
Wilson and session bootstrap intervals. Stress1minute added availability delay.
Replay signals has no live quotes/fills; do not claim option P&L or ignore fees
in a profitability claim. There is no profitability claim in this experiment.

Absolute acceptance for ANY detector, including baseline: >=30scored signals,
>=5complete independent sessions, event precision>=0.50, precision Wilson95lower
>=0.40, early-event recall>=0.20, false alarms/session<=2, median lead>=1minute.
Alternative must additionally have positive lower95% paired-session bootstrap
improvement in early-eventF1 versus baseline (5000 draws,seed20261022), and
nonnegative point earlyF1 difference under1minute extra delay. No minimum signal
count imposed on sparse baseline just to prevent a valid new detector from winning.
Acceptance thresholds are engineering targets for the user's early/low-noise goal,
not empirical win-rate claims from the PDF. No tweaking after outcomes.

If either sample/absolute/relative gate fails, declare DETECTION NOT_READY,
preserve the actual operational reader/notification infrastructure and stop adding
features or searching on this test. No new Pine strategy is claimed validated.
Only if all gates pass: integrate accepted model with common live safety/dedupe,
update matching Pinev6, perform focused parity/safety checks, and then roll out
existing service (no paid resources or trades). No automatic SPX contract advice
without actual fresh index/option data, regardless of ES research performance.
