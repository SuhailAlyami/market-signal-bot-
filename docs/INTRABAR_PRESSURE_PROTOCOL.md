# Amendment before intrabar development test / unused acquisition

The fixed1minute local-range repair failed on CONSUMED development.101raw
triggers produced10riskplans/0early matches; even94raw scored triggers before
risk gating matched32events but only1early, medianlead-1minute. Thus shrinking
stops would hide the timing defect, not fix it. No unused dates were acquired.

New resolution is actually available: nativeESU6 historical5secondTRADES,
720bars for Sept1onehour and5400bars for Sept2full brokerRTH. Both dates were
already development. The1D/5second request succeeded; no need for140hourly
requests or paid data. Use up to the SAME10consumeddevelopment dates first,
reuse the successful Sept2snapshot, maximum9newday requests, no connectiontests.

## Specific timing model, fixed before measuring

`intrabar-compression-v1`: pressure context from last31 contiguous COMPLETED
1minute candles, with positive minute volume/valid OHLC. It is known only at
their closing boundary and cannot be used by a5second bar that started earlier.
ATR is meanTR of last20completed minute bars;5minute/15minute close trend,
last5high/low, last20high/low and contraction<=0.65 are frozen for each nextminute.
Long pressure: lastcompletedminute bullish body, close in its upperquarter,
0<=last5high-close<=0.2ATR, trend5>0/trend15>=0. Short is symmetric.

Require TWO distinct consecutive completed5second closes beyond the frozen
5minute boundary by0.1ATR within that nextminute. Both bars must contain real
positive trade volume. Their combined10second volume divided by twice the
median of the12five-second bars BEFORE the pair must be>=1.2. This replaces
waiting for a whole newminute to confirm volume; never compare a partialminute
to whole-minute volume or weaken the1.2threshold. The second bar body must agree.
Reset confirmations at a new frozen context, on gap/zero-volume confirmation,
or when price returns through the buffer. No retrospective intrabar interpolation.

Long structural stop=min(lastpressureminuteLow,brokenLevel-0.1ATR)-oneES tick;
short symmetric. It protects the actual nearest pressure candle AND brokenedge,
not an obsolete outer5minute opposite extreme. Never clip a stop to fit risk.
Common current-price entry±0.05ATR, tick rounding, risk<=2ATR,targets1R/2R,
10minute active lifetime/5minute cooldown remain. No P&L/fill claim.
Only a risk-accepted plan enters ACTIVE: a rejected/unpublishable candidate must
not occupy an active position for10minutes. The previous replay latched even
invalid risk candidates; this is a scheduling defect, not permission to clip risk.

## Guard against falsely claiming earlier signals

Build full minutes only from12original5second observations (no fill). Zero-volume
5second flat bars are allowed in source aggregation but cannot confirm a trigger;
they do not prove fresh trades. Retain all original source rows and gaps.
Both models use the SAME aggregated minute data and same independent movement
events/anchor/target/horizon. For PRIMARY scoring, conservatively refine onset
to START of the earliest positive-volume5second bar touching the25%movement
threshold. Preserve1minute onset separately for audit. This is earlier, stricter
than claiming lead versus a minute's closing timestamp. Current and new detectors
receive the exact same refined labels. Keep the scorer's original conservative
target-minute-start deadline. A5second decision is indexed to the last COMPLETED
minute, never its still-forming minute, so it cannot match an unknown futureanchor.
Also report coarse labels to reveal any timing alias. Availability stress+1minute.

Development result must beat baseline refined earlyF1 before spending20unused
July20–Aug14dates. No parameter grid or change after unused outcomes. Code and
this amendment must be committed BEFORE development performance is measured.
Acceptance criteria remain ALL the prior absolute/paired gates, including
>=30signals,precision>=.50,Wilsonlower>=.40,earlyrecall>=.20,medianlead>=1minute,
false/day<=2,positive pairedlower95;sourcecoverageandstressunchanged. No more
lenient definition ofearly or readiness for the faster data.

If no justified improvement, retain the negative evidence and identify the
specific missing information/validation sample before any further proposal.
Do not call the broader improvement task complete just because a model failed.
If accepted, live needs actual fresh5second bars and brokerquote safeguards;
matching Pinev6 must use the same5second clock/closed1minute context and clearly
state TradingView data/timeframe availability. No new paid service or trade.
