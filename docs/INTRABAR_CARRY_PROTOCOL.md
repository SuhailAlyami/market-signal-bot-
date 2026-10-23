# Frozen cross-minute sweep hypothesis

Registered before running this candidate. All September observations are consumed
development, including the 54,000 five-second bars. No fresh proof is claimed.

Diagnosis: the v1 loop resets an unfinished sweep whenever the completed-minute
context index changes. This is a clock boundary, not price invalidation. The
83 scored signals capture only 9/223 events early. Adding a confirmation filter
to that fixed signal list cannot reach the unchanged 20% global early recall.
The reference separates accumulation/manipulation/distribution; it does not
require all three phases inside the same wall-clock minute.

One change: retain the original completed-minute range, ATR and sweep state
across minute boundaries, up to the existing ten-minute lifecycle duration from
the FIRST sweep close. A new extreme updates the actual stop reference and
CISD-open, and resets the two-close counter, but never extends the timeout.
At timeout discard the state and use only the then-current completed context.
Reject two-sided sweeps and gaps as before. No reused old range can claim a new
sweep time. All volume, contraction, sequence, risk, cooldown and decision-time
checks remain fixed. No continuation trend filter is added to reversal.

First run once on the consumed ten September sessions, against both v1 and
continuation with identical conservative five-second onset labels. No parameter
search. Report global recall, precision, false alarms, lead time and source
coverage, not only selected favorable trades. The unused July20-Aug14 sample
is reserved: do not spend it unless this candidate meets the existing absolute
development quality gates, not merely a positive paired F1 difference. Final
promotion still requires the full independent acceptance and latency stress
specified in MICRO_RANGE_PROTOCOL.md. Otherwise NOT_READY, no live/Pine change.

This is a falsifiable state-lifetime repair, not a claim of full PDF confluence
or real volume-profile reconstruction. Rich trade/quote data availability probes
are not evidence of predictive quality.
