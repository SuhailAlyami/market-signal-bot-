# SPX-only price WATCH v1: frozen development hypothesis, NOT_READY

The owner now requests SPX alone. Native cash SPX IND prices are the only
detector input. ES/NQ outages, helper volume, 15-minute companion trends and
an options-chain initialization must not stop the SPX price observer.

## Rules fixed before this run's market replay

Evaluate completed standard one-minute native SPX bars only, with 31 valid,
contiguous observations and positive prior20 true-range mean. No volume value
is fabricated for an index and no helper is substituted. Require native SPX
symbol and IND metadata; SPX500 CFD and ES futures are different instruments.

At the current close, give sweep/reclaim precedence:

* UP: current Low < prior20 Low < current Close, bullish body.
* DOWN: current High > prior20 High > current Close, bearish body.
* A bar sweeping both sides is ambiguous and produces no candidate.
* Otherwise UP/DOWN local break: close beyond prior3 High/Low with matching
  body direction. No requirement to reach the prior20 boundary or remain
  within0.3ATR of it. This is an observed first-stage break, not a forecast.

Freeze the breached level and current-bar opposite wick as invalidation.
Existing two buffered completed-close confirmation, ten-minute expiry and
five-minute cancellation cooldown remain explicit research lifecycle rules.
A valid opposite price candidate cancels the previous scenario before its
confirmation and may start on the same closed bar, bypassing the old state's
cooldown. Completed-bar dedupe still applies. This SPX-specific behavior does
not change the ES lifecycle. No immediate-entry performance is implied.
No threshold search is authorized by this report.

Use the actual NYSE calendar, DST and early closes for native cash SPX. Outside
the cash session no stale index is called a current observation. This does
not restrict a futures instrument under a different identity.

## Operational changes and scope

The SPX primary path uses a new state namespace so an ES-supported historical
state cannot silently control the new hypothesis. Its compatibility es_fetch
argument is not called. It starts index subscriptions without requesting an
option chain. The old helper function and explicit option sampling utility
remain for compatibility/testing, but the new default path never calls them.

Standalone local command (official TWS Python SDK and logged-in Read-Only
Gateway required): `python spx_primary.py --state-dir .hunter-state/spx-only`.
This starts SPX directly; do not use the older gateway_hunter launcher to claim
SPX-only operation, since that launcher also starts ES. Ctrl+C stops the
standalone monitor; `--seconds 120` bounds an explicit local smoke run. No
Windows-host launch or native SDK handshake is claimed by this change.

Every price event remains NOT_READY, notify_eligible=False. The primary logs
events and latest rejection reasons independently of whether an option quote
exists. It does not manufacture a complete option plan or send the unvalidated
new model to the old recommendation sender. Existing ES execution paths are
not modified. This draft must not be described as a deployed improvement.

The existing ES/Pine script remains a legacy comparison, not the port of this
new SPX-only hypothesis. Its source fingerprint must track changes to shared
runtime; a matching hash alone does not prove algorithmic parity.

## Evaluation before any adoption

The Oct22 screenshots and existing September results are consumed development.
Acquire actual SPX history once, preserve provider timestamps/semantics and
exclude the partial bar using provider chart_end. Report each candidate's
decision time (bar end), direction, pattern, and rejected/invalid observations.
Describe a single incomplete session as a diagnostic replay, never a holdout.
Compare causal original SPX price eligibility on the SAME data; because the
old production rule additionally requires ES, do not fabricate an old signal
list or an ES-free production baseline.

Future quality testing must retain movement definitions, matched timing,
false alarms, misses, lead and delay sensitivity, and use untouched sessions
only after a fixed candidate clears development gates. A shape on today's
chart or a passed synthetic regression is not such evidence. No profitability,
confidence percentage, option bid/ask or recommendation is inferred.
