# Volatility context for SPX research candidates

The user's screenshot labels historical/realized volatility 10.8% and recent
implied volatility 13.5%, with the market closed. The measurement windows,
annualization conventions, source timestamps and specific IV tenor are not
established by the screenshot. These figures are not ingested as live inputs.

Realized volatility describes past movement; implied volatility is inferred
from option prices. A difference is useful research context, not evidence of
an upcoming directional explosion, an underpriced option or a safe entry.
An option can lose premium to time decay or falling IV despite a correct
underlying direction. Far-out-of-the-money strike and far expiration are
separate dimensions. This SPX selector remains restricted to 0DTE; a request
for farther expiry requires a separately specified and evaluated strategy.

Each selected, independently verified fresh SPX quote now includes:

- OTM distance in index points and percent.
- Long-option expiry breakeven at the quoted ask, before commissions/fees.
  This is expiry payoff arithmetic, not an intraday take-profit threshold.
- Premium at ask and maximum premium loss before fees, with the SPX multiplier.
- Explicit unavailable IV/RV, Greeks, exact expiry time and profit probability
  when they have not been supplied/verified. No invented values or assurance.

`OptionQuote` optionally accepts documented `VolatilityObservation` inputs.
`compare_volatility` requires positive finite annualized decimal values, source,
aware timestamp, same underlying, same annualization convention and matching
IV tenor/RV lookback length. The matching-window requirement is deliberately
conservative; it does not assert that past and future distributions match.
Freshness is independently checked; stale/future or mismatched inputs produce
UNAVAILABLE with a reason. The output is an observed ratio/difference only:
no entry signal, direction, confidence score or claim of profit probability.
The selector still ranks by ATM distance and spread. Volatility does not promote
a far strike or bypass its existing live quote gates.

The current IBKR adapter does not populate these optional normalized volatility
observations: field-specific units, horizons and timestamps have not been
verified. A `REALTIME` last price alone cannot establish those facts. Therefore
actual connected reports explicitly mark this comparison UNAVAILABLE. No web
scraping, screenshot transcription, guessed Greek or new order tool is added.

The screenshot's arithmetic ratio would be 1.25 and its difference 2.7 percentage
points **if** the measurements were comparable. Those numbers are tested as
illustrative arithmetic only, not treated as a verified comparison or a signal.
No claim of detector improvement is made until separate future data evaluate it.

Primary reference: Options Industry Council,
https://www.optionseducation.org/advancedconcepts/volatility-the-greeks
