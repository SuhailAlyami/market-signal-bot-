# Five-date prior-history result — 2026-10-29

NOT_READY. Rules fixed before results in docs/CFD_PRICE_HISTORY_PROTOCOL.md (253733959322422ad69d364744aa3c22dc926e1a). Actual Pine compilation and table rendering observed. No rule/parameter was retuned. Raw bar export was unavailable; these are transcribed chart-table results, not an independently replayed data set. Coverage counts below are observed completed bar-close counts, not a guarantee of complete expected sessions. Broker session breaks and missing data have not been separately reconciled.

| Date KSA | Model | Bars | Decisions | Target | Stop | Timeout | Both | Gap/input | Pending |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Oct20 | RANGE | 1405 | 35 | 19 | 16 | 0 | 0 | 0 | 0 |
| Oct20 | FAILED | 1405 | 66 | 28 | 38 | 0 | 0 | 0 | 0 |
| Oct20 | BODY | 1405 | 136 | 59 | 75 | 1 | 0 | 1 | 0 |
| Oct21 | RANGE | 1426 | 37 | 11 | 26 | 0 | 0 | 0 | 0 |
| Oct21 | FAILED | 1426 | 72 | 40 | 31 | 1 | 0 | 0 | 0 |
| Oct21 | BODY | 1426 | 134 | 57 | 76 | 1 | 0 | 0 | 0 |
| Oct22 | RANGE | 1424 | 39 | 16 | 22 | 1 | 0 | 0 | 0 |
| Oct22 | FAILED | 1424 | 57 | 19 | 35 | 1 | 2 | 0 | 0 |
| Oct22 | BODY | 1424 | 134 | 59 | 74 | 1 | 0 | 0 | 0 |
| Oct23 | RANGE | 1429 | 33 | 12 | 21 | 0 | 0 | 0 | 0 |
| Oct23 | FAILED | 1429 | 69 | 38 | 30 | 0 | 1 | 0 | 0 |
| Oct23 | BODY | 1429 | 136 | 49 | 84 | 1 | 2 | 0 | 0 |
| Oct26 | RANGE | 1378 | 41 | 23 | 16 | 2 | 0 | 0 | 0 |
| Oct26 | FAILED | 1378 | 70 | 32 | 38 | 0 | 0 | 0 | 0 |
| Oct26 | BODY | 1378 | 134 | 62 | 70 | 2 | 0 | 0 | 0 |

All15 rows conserve counts: decisions=target+stop+timeout+both+gap+pending.

Totals: RANGE185 decisions,81 targets,101stops,3timeouts; FAILED334 decisions,157targets,172stops,2timeouts,3ambiguous; BODY674decisions,286targets,379stops,6timeouts,2ambiguous,1gap. Target-first fraction among target/stop-only observations: RANGE44.5%, FAILED47.7%, BODY43.0%. These exclude explicitly retained other outcomes; they are not profit rates, independent statistical estimates or early-event precision/recall. Samples overlap, and different model-selected timestamps mean this is not a paired-event causal comparison.

RANGE beat the body's target-first fraction on Oct20 and26, but underperformed on Oct21,22 and23. FAILED was stronger on21/23 and weaker on20/22/26. Thus the earlier promising Oct27/Oct29partial range-readiness result did not demonstrate stable superiority across older sessions. Preserve both positive and negative dates; no production winner chosen, no subscription justified.

These are broker CFD hypothetical path boundaries: next-bar Open reference, target1priorATR, stop0.75ATR, ten consecutive minutes, samebar touches ambiguous. No fills/costs/options P&L. Some corresponding SPX/ES dates were already consumed in earlier research; this batch is historical robustness/development evidence, not untouched independent validation. Oct19 excluded before results due01:00 loaded start;27/28/29 were excluded from this fixed batch. No cherry-picked day removal.

Source: tradingview/Suhail_Hunter_PRICE_HISTORY.pine. Exact table values incl timeout means retained in artifacts/cfd_price_history_20261029/results.json. Future work must use independently reconciled raw data and truly prospective validation; increasing historical sample does not itself repair the absent market-edge evidence. No paid plan, order or alert activated.
