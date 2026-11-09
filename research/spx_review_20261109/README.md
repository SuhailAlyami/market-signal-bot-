# SPX detector review (2026-11-09) — decision: STOP this hypothesis family

Scope: 116 CONSUMED sessions (2026-05-19..11-04). Everything below is a research finding, NOT independent validation. Sessions 2026-11-05/06 and all newly collected sessions were not read. Files: `diagnose.py/json` (existing wave_capture outputs, no new detector), `protocol.json` (committed in 7502cfb before the screen), `state_gate.py/json` (one run, no variants).

## 1. Do labels and "early capture" match actionable early detection? No.
- Labels are a retrospective zigzag (10-pt reversal, legs >=20 pts). A pivot is known only after a 10-pt reversal; "early" (<=25% of the leg consumed) is measured from that hindsight-optimal pivot.
- The detector (close-confirmed directional change) and the label share a construction, so matching is partly circular. Random decision times with the same count/cooldown/side: matched<=75% 199 vs 125 random, but early 48 vs 42.9 random (107/500 draws >= actual).
- Matched legs: median lag 15 min, median 37% of the leg already consumed, only 24% of matched are early; median remaining move after the signal 18.8 pts.
- Actionable forward outcome from the decision (delay 0, 592 trades): direction after 30 min correct 49.5%; target (2R) reached before stop in 25.3% of resolved trades vs 33.3% needed at zero cost; mean gross +0.256 pt/trade, session-bootstrap 95% [-0.53, +1.11] (indistinguishable from 0).

## 2. Why false alarms and losses stay high
668 signals / 116 sessions = 5.8 per session; 469 unmatched (4.0/session). Median R is 5.54 pts: 42% of signals sit at the 5-pt floor, so the stop is inside bar noise. A 1-pt round-trip cost is 18% of median R against a mean gross of 0.26 pt. 47% of trades end at the stop; net at cost 1 is -440.2 pts (gross +151.8).

## 3. Can five-minute bars resolve the required timing?
Legs are long (median 55 min, p25 30 min; only 9% <=15 min, 29% <=30 min), so 5m bars can see them after confirmation but not their onset: median lag 15 min; with a 15-min-late feed (archive declared delayed=900 s; Yahoo's delay is undeclared) 29% of legs are over before a signal could be acted on. Resolution is not the binding constraint: CUSUM on 1-min data (28.1% / 18.6% success vs momentum 27.4% / 19.4%), ES/NQ half-minute pilot, 30-s residual, ES lead and structure-wave experiments were all negative on retained results.

## 4. One new hypothesis, one bounded screen (result: STOP)
Hypothesis: signals only have non-negative gross when volatility is above the protocol floor (R > 5.0, no fitted threshold). Pre-registered C1-C4:
| Criterion | Result |
|---|---|
| C1 gated mean gross > 0 in both blocks | FAIL: older +0.99, recent -0.45 pt |
| C2 gated minus floor-bound gross-in-R, bootstrap lower bound > 0 | FAIL: +0.053 R [-0.132, +0.233] |
| C3 beats within-session random direction (cost 1), lower bound > 0 | pass: +359.3 pts [87.5, 668.1]; random-direction net -523.2 |
| C4 gated pooled net at cost 1 > 0 | FAIL: -163.9 pts (343 trades; +7.6 at cost 0.5) |
Reading: direction carries a little information versus random direction at the same times (gross about +0.5 vs -0.5 pt/trade in sample), but it is not stable across blocks (recent block negative; older 5-min / recent 1-min raw, confounded with time) and is smaller than cost. Pre-test power note said C2 would be inconclusive; it was.

## Decision
Stop this hypothesis family (price-only, close-confirmed directional detection on delayed SPX index bars). No further tuning, gating or filters on these 116 sessions. A different approach needs a different information source (timely data with receipt times, and a verified option chain), which is not available at no cost. Keep only the free collector running; if >=55 unused sessions accumulate, evaluate the frozen control once against the random-timing and always-up/reversed baselines as a falsification check, not as a promotion path. Status NOT_READY, alerts OFF.
