# Capital.com chart research — 2026-10-29

Use tradingview/Suhail_Hunter_CAPITALCOM.pine only on standard one-minute CAPITALCOM:SPX500 candles. This is a separate research universe: broker CFD prices and broker tick counts, not cash SPX or exchange volume. Relative activity compares broker ticks to their own prior median, without zero filling. No ES/IBKR request is made. Existing price thresholds are unchanged but NOT validated for CFDs; NOT_READY remains. Missing/nonpositive tick volume prevents setups. No fabricated strike, premium or SPX price conversion.

Observed in the signed-in TradingView UI: CAPITALCOM:SPX500 market open, one update every second, Volume · Ticks. This is a UI update indication, not independently verified provider trade latency. Original SPX/ES symbol guards remain unchanged in the original script. Research alerts are off by default, and DELAYED declaration suppresses them. Saving was blocked by account plan limits; no subscription purchased or permanent mobile installation claimed.

Capital.com describes extended index-CFD pricing based on live futures, potentially differing from official cash index prices: https://capital.com/en-int/ways-to-trade/24h-trading
