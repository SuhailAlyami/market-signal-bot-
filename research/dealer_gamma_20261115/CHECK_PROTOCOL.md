# Limited technical check (owner decision B) — registered 2026-11-15 before running

Scope: one technical coverage check during an open NYSE session via the claude.ai IBKR connector. NOT a daily collection, NOT a hedging map, NO signal, NO GEX value, NO comparison with breadth (unproven). No orders, alerts, watchlists or subscriptions.

When: once, about 45 min after the 2026-11-16 open (15:15 UTC = 18:15 Riyadh). If the session is closed or the connector is unavailable, record that and stop; do not retry on other days without a new decision.

Procedure (single pass):
1. SPX index snapshot (last, top_status) with request/receipt times (UTC).
2. 0DTE SPXW expiration of that day; strikes from round5(spot)-50 to round5(spot)+50, step 5 (expected 21 strikes, 42 contracts).
3. For every contract, one snapshot requesting option_open_interest, option_greeks, bid_ask, top_status; record receipt time.
4. SPX index snapshot again at the end.

Report (counts only, per field): contracts listed by the chain; contracts that returned anything; OI present (call/put field as expected); greeks present; bid/ask present; top_status distribution (REALTIME / DELAYED / FROZEN / FROZEN_DELAYED / REJECT / missing); first/last receipt time and total duration; SPX status at start and end.

Pass criterion for "technically feasible for a later protocol": >= 95% of listed contracts return OI and greeks, and top_status is REALTIME for the option snapshots. Anything less is recorded as the limitation it is. Passing still establishes no edge and no hedging map.
