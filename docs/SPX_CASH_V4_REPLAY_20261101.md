# SPX cash v4 replay — 2026-11-01

NOT_READY. Raw data acquisition succeeded through connected IBKR tools without user intervention. Resolved SPX exactly, US CBOE IND contract 416904. ONE_MONTH/ONE_MIN was rejected by the 1000-bar limit; a subsequent step_count=1000 request succeeded. No limits bypassed, subscriptions purchased, or trades placed.

Source Last, chart_step 60, reported coverage 2026-10-28T16:20:00Z through 2026-10-30T20:00:00Z. Historical data only; no LIVE_VERIFIED claim. Source response retained in artifacts/spx_cash_v4_20261101/raw.json, exact normalized input in spx.csv, per-event outcomes in result.json.

Unchanged v4 acceleration and event audit reference replay: 67 signals; 21 target-first, 43 adverse-first, 2 ambiguous, 1 gap, 0 timeout, 0 pending. Counts conserve 67=21+43+2+1. Target share of resolved unambiguous outcomes =21/64=32.8125%. This is a fixed path diagnostic, NOT early-detection precision, P&L or an independent holdout result. It does not meet the 70% goal. Price reference is next minute Open; target1priorATR/adverse0.75priorATR within10 contiguous bars. Input CSV SHA256 bd1c455d393694b0fb878659a1f528b450f868bb1b0304a1722bdf610d13b77d.

This is cash SPX, separate from CAPITALCOM CFD. Do not combine its counts with CFD's earlier 35-event table. This is partial 3-date coverage, not 20 complete sessions. Day boundaries and gaps are not filled; the input is chronological. Replay retains overlapping observations as defined in the audit; they are not independent samples. No threshold optimized in this run. Frozen source files fetched from feat/capitalcom-cfd-research-20261029: cfd_causal_reference.py,cfd_acceleration_v4.py,cfd_path_scoring_v2.py,cfd_v4_event_audit.py.

Reproduction: python3 cfd_v4_event_audit.py artifacts/spx_cash_v4_20261101/spx.csv

Next: use retained per-event failures to propose training-only feature filters and compute the separately frozen movement-onset/early matching metric. Check retained successes sacrificed by each filter. Reserve new chronological data for validation and do not recast this inspected sample as untouched. No active runtime or alert delivery has been established.
