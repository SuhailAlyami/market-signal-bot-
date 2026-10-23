# Fixed native ES onset forecast experiment — 2026-10-23

Reason: fixed compression/pressure predicates produced too many false warnings
and mostly reactive matches. Previous linear research used different proxy and
cross-market inputs. This experiment asks a narrower supervised question on the
available native observations: do eight causal continuous measurements separate
the minutes BEFORE onset from ordinary minutes? This is not a parameter search.

Input is the retained native ESU6 five-second source, aggregated without filling
into complete minutes. Source SHA2565704e0a957c7d0b8a6e67902304a7cc15ec4ddb0c5e99d6a51821630a8886346.
All ten September sessions are CONSUMED DEVELOPMENT. First four sessions
Sep1,2,3,4 fit one model; remaining six Sep8,9,10,11,14,15 are chronological
development validation. They are not untouched test data. No model/threshold
selection on the six later sessions, no refit, no grid, no new acquisition.

Reuse the SAME223 frozen fine-onset movement labels, strict anchor/target/horizon
matching, eligible cash-session observations and boundary embargo. Training
labels are NONE/UP/DOWN: a minute qualifies for a directional class only when
the corresponding event anchor is already reached, its target is within the
existing ten-index horizon, and onset is1–3minutes AFTER the completed decision.
Labels may use later outcomes for training only; input features never do.
Ambiguous conflicting directional labels are excluded, not assigned by a future
tie-breaker. Require at least10training examples per directional class; otherwise
report insufficient support before fit. No post-onset entry becomes an early
warning by relabeling. No pre-anchor scoring amendment to rescue this model.

Eight fixed features:5/15minute return divided by prior20ATR, current signed
body/ATR, current full range/ATR, current volume/prior20volume median,
last5range/last20range, close position inside last5range scaled to[-1,1],
last5range/ATR. All end at the completed decision candle. Zero ranges, missing
observations and gaps fail closed. Standardization and class weights fit on
first-four-session rows ONLY. Reuse existing numpy multinomial fit_model with
L2=1,300iterations; it is an uncalibrated score, not a win probability.

WATCH requires a directional winning class with score>=0.65 and margin>=0.1
above the opposite direction. These constants reuse existing research values,
not chosen from this result. Emit on transition into that directional regime;
do not rearm the same direction until its score falls below0.5 or a valid
opposite directional regime appears. Invalid context resets the regime. Model
state is independent of entry acceptance; no entry/option contract is invented.
The existing separate entry and live senders are untouched.

Report training class support and both phase metrics; primary comparison on
the six later development sessions is against saved SETUP replay with rejected
plans released. Measure movement precision/early recall, ALL-match median lead,
false/session, Wilson bounds, paired-session earlyF1 interval and+1minute delay.
Keep the existing absolute gates:>=30signals,>=5sessions,precision>=50%,
Wilsonlower>=40%,earlyrecall>=20%,medianlead>=1minute,false<=2/session,
positive lower paired95% earlyF1 gain and nonnegative delay-stress gain.
If these fail, no independent acquisition or live promotion. If they pass,
freeze the serialized model and source BEFORE acquiring July20–Aug14 and apply
the full independent acceptance there. New matching Python/Pine is conditional
on that independent result, never on development/CI. No infrastructure rechecks,
paid services, Telegram test, orders or changes to the operating monitor.
