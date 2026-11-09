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

Pre-registered next test: SUPERSEDED by the audit below (sample target corrected before any holdout data was read).

Timestamp observation: at 2026-11-09 19:44 UTC, Yahoo's meta.regularMarketTime for ^GSPC was 1.5 s old at receipt (0.9-5.2 s for the stocks). regularMarketTime is Yahoo's stamp of its last regular-market quote update; it is NOT a bar boundary and NOT a verified delivery latency.

## Validity audit (2026-11-09, `audit.py` -> `audit.json`; development dates only, rule unchanged)
| Check | Finding | Verdict |
|---|---|---|
| Timestamp meaning | 390/390 5m bars equal the 1m bars [t, t+5m): chart timestamps are bar STARTS (0 matches as bar ends). | pass |
| Closed-bar availability | Feature uses stock closes at the decision-bar close and 15 min earlier; no partial bar; same instant as the SPX decision. Real delivery delay unmeasured. | pass (assumption) |
| Entry after availability | Entry = open of the next 5m bar. One bar later: high +0.71 vs rest -0.08 (diff +0.79, was +1.80). | pass, but effect halves |
| Missing stocks | 57/57 sessions complete for all 11 symbols, 0 nulls, 0 signals dropped; 2-37 zero-volume bars per stock with moving prices (volume field gaps, not stale prices). | pass |
| Stock selection | List fixed before results but chosen with today's knowledge of the largest caps (membership look-ahead); no alternative universe tested. | limitation |
| Confounding with SPX's own 15-min move | corr(agreement, aligned SPX move) = 0.56; high-minus-rest stays positive in all three momentum terciles (+1.60, +1.18, +0.80; small cells). | partly independent |
| Session-clustered uncertainty | Session bootstrap [+0.21, +3.34]; 5-session block bootstrap [-0.12, +3.50] includes 0. | weak |
| Prior multiple testing | One-sided bootstrap p = 0.013; 36 preregistered protocols in research/; Bonferroni bound p = 0.48. | weak |

Verdict: no implementation defect found; statistical evidence is weak. The rule stays REJECTED as a trading rule and the feature is retained only as a frozen candidate for the forward test.

Forward test (pre-registered in `forward_protocol.json`; not run):
- Frozen logic is in `breadth_core.py` (moved verbatim); `inputs.py` holds input loading and date selection only. `python run.py` reproduces `result.json` byte-for-byte and `audit.py` reproduces `audit.json` (checked by `test_forward.py`).
- Input: the collector store `breadth5m/bars5m.json` on `data/spx-collection` (5m bars for ^GSPC and the ten stocks, first complete read canonical). Only sessions >= 2026-11-05 where all 11 symbols are complete are used; others are excluded with reason.
- Single look: `python run.py --forward <store>` counts high-agreement events without computing outcomes and refuses to score below 190 events. The 190 figure is conditional: 80% power only if the true difference is +1.8 pt; ~757 events if it is half.
- Acceptance requires ALL of the original C1-C4 (including C2 net at cost 1 > 0 and C4 beating random direction) plus C5 (5-session block bootstrap lower bound > 0). A positive group difference alone is insufficient. Pass still means NOT_READY; alerts stay OFF.
