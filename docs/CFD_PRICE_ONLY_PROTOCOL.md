# Frozen price-only CFD research — 2026-10-29

No production selection, alerts, trades or subscriptions. No tuning after outcomes. CAPITALCOM:SPX500 standard1min OHLC only. Fix test date 2026-10-27 00:00–2026-10-28 00:00 Asia/Riyadh; this is a previously untested CFD-date transfer diagnostic, not chronological forward validation. Oct28 is already consumed; do not use it to select these parameters. Oct29 prospective validation is not yet run.

Prior ATR20 = SMA true range over20 bars ending before current bar. Prior five-minute high/low and prior three-minute high/low exclude current bar. Require31 consecutive completed one-minute positive consistent OHLC bars. Do not use volume, external ES feed, partial candles or provider age claims.

M1 RANGE_READY: prior three-bar high-low width<=1.5 prior ATR20; current Close inside prior five-bar range and within0.25ATR of one edge; current candle range<=1ATR; direction agrees with current body and previous close. Up/down exclusivity required; don't confirm with two later closes.

M2 FAILED_BREAK: wick sweeps one edge of prior five bars then closes back inside, body agrees with reversal, close lies in directional outer40% of current candle; reject simultaneous sweep of both edges and range>2ATR.

BASELINE: direction of current nonzero candle body. All three evaluated with their own ten-minute decision-time cooldown, no overlapping pending observation per model, and identical valid-input gates. Earliest next-bar Open is reference only, no fills. Fix target1ATR, adverse boundary0.75ATR, horizon10 consecutive minutes. Both levels touched in the same bar = ambiguous, never count a win. Gaps censor. Report target-first, stop-first, timeouts, ambiguous, gaps, pending, plus mean signed terminal points among timeouts. These are hypothetical underlying CFD path observations with no spread/fees/slippage and no option P&L. More target hits do not establish early-event precision/recall or market edge. Retain all models including negatives and empty results; no winner selected from this small sample.
