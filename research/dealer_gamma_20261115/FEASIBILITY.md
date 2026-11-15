# Dealer gamma (GEX) feasibility via the IBKR connector — 2026-11-15 (Sunday, market closed)

Read-only checks through the claude.ai Interactive Brokers connector. No orders, alerts, watchlists or subscriptions. Nothing in the detector, collector or frozen forward test changed.

| Check | Result |
|---|---|
| SPX index contract | 416904 @ CBOE resolved |
| SPX last | 7560.87, top_status FROZEN_DELAYED (weekend; real-time entitlement not shown) |
| Option expirations | daily SPXW listed (next: 2026-11-16, 11-17, ...), monthly SPX 2026-11-19 |
| 0DTE chain structure | 2026-11-16 SPXW strikes 7535-7585 step 5 returned |
| Open interest per contract | YES: 7560 call OI 188, 7560 put OI 549 |
| Greeks per contract | YES: gamma 0.00462 (both), call delta 0.418, put delta -0.582; bid/ask returned (frozen) |

Conclusion: the inputs for a dealer-gamma (GEX) regime and level (open interest x gamma per strike) are available from the owner's IBKR account. Open interest is end-of-day, so a pre-open GEX map does not need a real-time feed.

Constraints found:
- One snapshot call per option contract; a usable map (about +/-150 points, several expirations) needs hundreds of calls per day. Feasible through the IB Gateway/TWS API scripts already in the repo (owner machine), not practical through chat calls, and not reachable from GitHub Actions (connector lives only in Claude sessions).
- Greeks/IV are IBKR model values, not exchange data; dealer positioning sign is an assumption (customers assumed long puts / short calls is the common convention, not observed).
- No free historical open interest: the hypothesis can only be tested forward, after a protocol is committed.

Status NOT_READY. Next step requires an owner decision (see owner report).
