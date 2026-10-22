# Primary SPX, actual options, ES confirmation — 2026-10-22

The primary target is SPX and its actual0DTE options. ES is auxiliary and never
converted to an SPX price. A separately named ES alert is still an ES underlying
research alert; it does not certify an SPX opportunity.

## Native data and permission evidence

Fresh native Gateway check at04:45UTC resolved SPX/CBOE416904, SPXW chain metadata
and sampled CALL/PUT contracts. MarketDataType1 was accepted with no request
permission errors. Index last-trade timestamp was0/missing, so current index
freshness was NOT verified. Options can update while the cash index does not;
buying an additional subscription is not proved to solve that observation.
No missing paid entitlement has been demonstrated and no subscription purchased.
If a future API entitlement error appears, report the exact error/package and
current account-specific price before approval; do not assume a fee from type1.

`spx_primary.py` continuously subscribes to native SPX1min OHLC and a bounded
sample of three nearby strikes/both rights from the real same-day SPXW ladder.
This verifies a sampled nearby book, not every contract in the full chain.
It reconnects after transport/history failures and refreshes the sampled expiry
and strikes periodically. Status/journal live in `.hunter-state/gateway/spx/`.
The primary summary is relayed to service health without exposing option quotes.

Index freshness requires a genuine positive IB trade timestamp <=10seconds old.
SPX has no invented index Volume column: native validation is price-only. The
derived detector's relative volume explicitly uses the previous completed ES
minute, with exact timestamps and no forward fill; missing helpers block a setup.
SPX prices/levels/ATR remain SPX values throughout. ES5/15min trends must agree
both at setup and confirmation. Completed candles, volume, invalidation, two
buffered closes, expiry and cooldown remain mandatory.

SPX publication additionally requires a fresh actual same-day CALL/PUT matching
direction, positive uncrossed bid/ask, <=15% spread and <=1% moneyness. Each side
must show repeated callbacks; a single initial book snapshot is insufficient.
Both sides' local receipt ages and the underlying trade age must be <=10seconds.
Exchange bid/ask timestamps/transport latency are not independently verified.
Message entry/stop/targets are explicitly underlying SPX index levels; option
bid/ask are actual observed premiums. No option exit premium is synthesized.
No order/account request is made. Research edge remains NOT_READY.

## Rule correction and Pine delivery

Runtime v2 uses the preceding20 completed-bar range consistently, rather than
calling a partial180bar buffer a complete prior day/session. This removes
additional nearby candidate levels and does not lower any threshold. Frozen
research code/results remain intact and are not relabelled as validation of v2.
Parameters live in strategy_rules.py; lifecycle/plan modules use the same contract.

Deliverable: `tradingview/Suhail_Hunter_ES.pine`, Pine Script v6, standard1minute
candles. Use SP:SPX for primary index visualization and CME_MINI:ESZ2026 as the
explicit ES helper matching the current native December2026 contract. For an ES
underlying view, apply it to that exact ES contract. ES1! roll adjustments and
TVC index proxies are not equivalent inputs. Keep helper expiry aligned on roll.

SPX helper requests use previous completed ES values with an explicit matching
timestamp. Setup, buffered confirmation, elapsed-time lifecycle and complete
underlying plan checks mirror Python. A SHA256 source fingerprint check in CI
requires updating the Pine port whenever rule/lifecycle/plan sources change.

Important differences: TradingView and IBKR have separate feeds/entitlements,
receipt/clock/retention gaps and outage cancellation timing. Pine has no verified
IBKR options book or durable cross-restart delivery state. SPX alerts are WATCH
only in Pine, never a contract recommendation. Backend publication rechecks
current price/entitlement/freshness after processing; chart historical markers
cannot certify those live checks. Neither platform's software success proves edge.

The owner's promised Suhail_Hunter_ES.pine attachment was not received at time of
writing. This is a new reviewed port of the repository logic, not a claimed diff
against the missing attachment. Python/source consistency tests ran; the actual
TradingView proprietary compiler/editor was not accessible, so compilation and
Add to chart on the user's TradingView account remain unverified. Import the file
in Pine Editor, Save, Add to chart; use once-per-bar-close alerts. Do not call a
source hash or Python test proof of successful TradingView compilation.

Official symbol/reference sources:
https://www.tradingview.com/symbols/SPX/?exchange=SP
https://www.tradingview.com/symbols/CME_MINI-ES1%21/?contract=ESZ2026
https://www.tradingview.com/pine-script-docs/concepts/repainting/
