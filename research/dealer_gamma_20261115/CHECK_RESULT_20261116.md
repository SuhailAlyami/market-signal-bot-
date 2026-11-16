# Limited technical check — result (2026-11-16, single pass)

Run per CHECK_PROTOCOL.md during the open NYSE session (XNYS confirmed), 15:19:37–15:22:03 UTC (146 s), via the claude.ai IBKR connector, read-only.

| Item | Count |
|---|---|
| Contracts listed by the 0DTE SPXW chain (7420–7520, step 5) | 42 |
| Contracts returning data | 42 |
| Connector rate-limit rejections (30 req/min), retried once successfully | 5 |
| Open-interest field present (call/put as expected) | 42 |
| Greeks present | 42 |
| Bid/ask present | 42 |
| top_status of option snapshots | DELAYED 42 |
| SPX index snapshot status, start / end | DELAYED / DELAYED (last-trade ~15 min old) |

- **Criterion A (OI on ≥ 40/42): PASS.** OI is end-of-day data.
- **Criterion B (REALTIME greeks, bid/ask, SPX): FAIL.** Every snapshot reported DELAYED.

Meaning: this account and connector give delayed (≈15 min) option quotes and greeks. That is no timely intraday dealer-positioning input. Passing A alone establishes nothing about an edge.
No GEX was computed. No signal, orders, alerts, watchlists or subscriptions were created.
Per protocol, this check is not repeated without a new owner decision.
Raw responses: raw_20261116.json. Counts: summary_20261116.json.
