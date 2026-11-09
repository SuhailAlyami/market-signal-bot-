# Constituent breadth as direction information — development result (2026-11-09)

Protocol committed in fc4f002 before results. 57 development sessions (2026-08-17..11-04), Yahoo 5m, DELAYED_RESEARCH_ONLY. SPX outcomes on these dates were consumed earlier; the breadth feature is new. Holdout (>= 2026-11-05) was not read. One run, no variants.

| Group (agreement of 10 megacaps with signal side over last 15 min) | signals | mean gross pt | direction after 30m | net @0.5 | net @1 | net @2 |
|---|---:|---:|---:|---:|---:|---:|
| all (control detector) | 294 | -0.08 | 50.0% | -170.0 | -317.0 | -611.0 |
| high (>= 8 of 10) | 121 | +0.98 | 53.7% | +58.0 | -2.5 | -123.5 |
| rest (<= 7) | 173 | -0.82 | 47.4% | -228.0 | -314.5 | -487.5 |
| high, first half | 57 | +1.23 | 59.6% | +41.5 | +13.0 | -44.0 |
| high, second half | 64 | +0.76 | 48.4% | +16.5 | -15.5 | -79.5 |

| Criterion | Result |
|---|---|
| C1 high minus rest gross, session bootstrap 95% lower bound > 0 | PASS: +1.80 pt [+0.26, +3.33] |
| C2 high net at cost 1 > 0 | FAIL: -2.5 |
| C3 high gross > 0 in both halves | PASS |
| C4 high beats random direction (cost 1), lower bound > 0 | FAIL: +102.8 [-20.0, +229.4] |

Decision by the pre-registered rule: REJECT as a tradable rule. Finding: breadth agreement separates signals (C1), the first feature in this repository to do so with an interval excluding zero, but the edge is about the size of a 1-point cost and weaker in the second half. Not independent validation.

Pre-registered next test (frozen now, before any holdout data is read): run `run.py` unchanged (this commit) on complete sessions >= 2026-11-05 once >= 40 exist; the only claim tested is C1 (high minus rest mean gross > 0, same bootstrap). Power note: the development interval half-width is ~1.5 pt at 57 sessions; at 20 sessions it would be ~2.6 pt, too wide to confirm +1.8, hence 40+. No alerts until a holdout test passes.

Latency observation (not verification): at 2026-11-09 19:44 UTC, Yahoo's own regularMarketTime for ^GSPC was 1.5 s old at receipt (0.9-5.2 s for the ten stocks). This is the provider's timestamp, not an exchange-verified time.
