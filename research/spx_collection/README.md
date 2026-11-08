# SPX bar collection (Yahoo ^GSPC 1m) — research only

- Access test 2026-11-08: `query1/query2.finance.yahoo.com` HTTP 200 after allowing the two hosts in the session environment (default egress policy returned proxy 403). Stooq, Alpaca data host and the Cboe CDN were unreachable (no response); Cboe also forbids automated extraction, so it is excluded.
- Yahoo gives 1m bars for the last 7 trading days only. A pull at least once per 7 trading days keeps sessions contiguous; daily is safer.
- `collect_yahoo_spx.py` stores each raw response (`data/raw/*.json.gz`), per-snapshot `requested_at`, `received_at`, `http_seconds`, provider `regularMarketTime`, last completed bar and its age (`data/snapshots.jsonl`), and complete regular sessions in the `opening_validation_raw` schema (`data/sessions.json`). First complete read is canonical; later differences are logged, never applied. Incomplete days are reported, never filled. Forming bars are dropped.
- Classification: DELAYED_RESEARCH_ONLY. Yahoo declares no delay or contract identity; historical bars have no per-bar receipt time (only the snapshot receipt time exists). Forward latency needs pulls during the session (not done: market closed today).
- `consumed_in_prior_research` marks sessions <= 2026-11-04. Unused so far: 2026-11-05, 2026-11-06 (do not tune on them).
- `compare_sources.py` -> `data/provenance_comparison.json`: Yahoo 1m closes equal the consumed 1m input (5 sessions, 1950 bars) and the 5m archive (6 sessions, 468 bars) within 0.0002. Identical official index values: this says nothing about vendor or delay.
- `collect_yahoo_spx.py --verify` audits stored sessions against the XNYS calendar (no network). Tests: `python -m unittest test_collect` (11 tests).
