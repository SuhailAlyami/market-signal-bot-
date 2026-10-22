# Pre-acceleration warning protocol, fixed before measurement

September native ES observations are consumed development. July20-Aug14 stays
unused. No live scanner or notification behavior changes in this experiment.

Documented cause: 212/223 movements lack early proximity to the 20minute edge;
104 target prices remain inside that range. Waiting for a breach and two later
closes cannot be a pre-breach warning. A pending/rejected execution plan must
not own the opportunity scanner's lifecycle.

Hypothesis: relative-volume directional pressure INSIDE a compressed local
five-minute boundary is an observable advance warning, distinct from entry.
Use the previously fixed 31-completed-minute context, ATR20 and contraction
five-minute-range/twenty-minute-range<=0.65. On a closed positive-volume native
five-second bar, close must still be INSIDE the frozen five-minute range and
within0.2ATR of one edge, body and completed five-minute trend point toward it,
and its actual volume>=1.2x median of the preceding12five-second observations.
No crossing, future pivot, two-close confirmation, HTF claim or option price
is needed for WATCH. Dual-edge proximity is ambiguous: emit neither direction.
Require contiguous source bars, known completed context and exchange hours.

WATCH is non-executable, with explicit state/source/time/direction/reference and
invalidation at the opposite frozen range edge. Dedupe same direction plus
tick-rounded original range pair until that range changes; separate up/down
episodes and alert identity from entry-plan state. Pending entries expire after
the existing10minutes, invalidate at the opposite edge, and require the existing
two subsequent distinct closes beyond0.1ATR for a separate ENTRY_CONFIRMED.
Common entry risk and structural stop stay unchanged. A rejected plan removes
ONLY its matching pending entry, records the rejection and never activates
position/cooldown. It cannot hide a new range episode, either direction.

Before measuring, compare WATCH to the original runtime SETUP stage (not only
its complete plans). Score entry confirmations separately. Keep the existing
movement universe and conservative five-second onset/target timing unchanged;
report signal count, movement and early precision/recall, lead, false/session,
paired-session intervals and +1minute availability stress. Warnings after onset
are not early. False warnings are warnings without a matching event. Do not
represent this matching statistic as option returns or fills.

Promotion requires the existing absolute30signal/5session/50%movementprecision/
Wilsonlower40%/20%earlyrecall/medianlead1minute/false<=2session criteria plus
positive paired95% earlyF1 gain over SETUP and nonnegative delay-stress gain,
on all twenty locked independent dates with complete source coverage. Development
cannot authorize promotion. If development fails, report it and diagnose the
specific bottleneck; do not optimize this threshold set on its outcomes.
