# Limited technical check (owner decision B) — registered 2026-11-15 before running

Scope: one technical coverage check during an open NYSE session via the claude.ai IBKR connector. NOT a daily collection, NOT a hedging map, NO signal, NO GEX value, NO comparison with breadth (unproven). No orders, alerts, watchlists or subscriptions.

When: once, about 45 min after the 2026-11-16 open (15:15 UTC = 18:15 Riyadh). If the session is closed or the connector is unavailable, record that and stop; do not retry on other days without a new decision.

Procedure (single pass):
1. SPX index snapshot (last, top_status) with request/receipt times (UTC).
2. 0DTE SPXW expiration of that day; strikes from round5(spot)-50 to round5(spot)+50, step 5 (expected 21 strikes, 42 contracts).
3. For every contract, one snapshot requesting option_open_interest, option_greeks, bid_ask, top_status; record receipt time.
4. SPX index snapshot again at the end.

Report (counts only, per field): contracts listed by the chain; contracts that returned anything; OI present (call/put field as expected); greeks present; bid/ask present; top_status distribution (REALTIME / DELAYED / FROZEN / FROZEN_DELAYED / REJECT / missing); first/last receipt time and total duration; SPX status at start and end.

Connector availability is part of the check: at the start record whether the IBKR connector tools load and the first call succeeds (yes/no, error text). If not available, record that as the result and stop.

Pass criteria (amended 2026-11-15 before running; evaluated separately, both reported):
- A. Open interest: OI field present for >= 40 of the 42 contracts. OI is end-of-day data; record it as the latest available value and do NOT require it to be real time.
- B. Timeliness: option greeks and bid/ask, and the SPX index snapshots, report top_status REALTIME (confirmed per snapshot). Any DELAYED / FROZEN / FROZEN_DELAYED / REJECT / missing status fails B and is counted.
Passing A and B means only "technically feasible for a later protocol". It establishes no edge and no hedging map.
