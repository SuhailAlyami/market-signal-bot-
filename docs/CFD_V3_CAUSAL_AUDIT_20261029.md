# CFD v3 causal reference audit — 2026-10-29

Status: NOT_READY. This is an engineering checkpoint after the v3 handoff, not a market-performance improvement claim.

## Added
- cfd_causal_reference.py: streaming reference for prior-only RANGE_READY and FAILED_BREAK features and confirmed-bar WATCH lifecycle.
- tests/test_cfd_causal_reference.py: ten tests covering prefix replay, future poisoning, nonempty FAILED_BREAK replay, known RANGE_READY fixture, direction mirror symmetry, malformed candles and gaps, partial-bar rejection, gap termination without same-bar rearm, close invalidation/cooldown, and ten-minute expiry.
- Existing four opening-aware PATH_V2 scoring tests retained.

## Validation
Command: python3 -m unittest discover -s tests -p 'test_cfd_*reference.py' (reference tests); also run test_cfd_path_scoring_v2.py.
Actual scoped local command: python3 -m unittest test_cfd_causal_reference.py test_cfd_path_scoring_v2.py from the delivery directory.
Result: 14 tests passed, approximately 0.05 seconds.
Seeded 180-bar synthetic fixture produces six RANGE_READY candidates, four WATCH starts and four END events. A separate deterministic FAILED_BREAK fixture produces an UP WATCH, so its prefix/future checks are not limited to an empty event stream.

## Interpretation and limits
These tests verify the new Python reference on synthetic fixtures. They do NOT establish byte-for-byte Pine/Python parity, Pine intrabar behavior, actual data freshness, event precision/recall, lead time, tradability, or market edge.
The delivered Pine v3 was not changed in this checkpoint; its previously confirmed compiler result remains the relevant Pine validation.
No thresholds were tuned and no historical results were re-scored. Original negative/weak results remain valid as recorded, not recast as PATH_V2 results.
No server alert was created or subscription purchased.

## Next gate
Obtain authorized raw CAPITALCOM:SPX500 OHLC with timestamps; reconcile source gaps; compare each Pine signal and lifecycle transition against this reference. Freeze an untouched prospective evaluation window and movement-onset definition before inspecting its outcomes. Historical chart-table transcriptions alone cannot satisfy reproducibility.
