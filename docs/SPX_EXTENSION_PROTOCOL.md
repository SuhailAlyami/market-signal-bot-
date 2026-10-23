# Limited SPX history extension — fixed before viewing extended outcomes

The connected native SPX IND/CBOE request for1000one-minute bars succeeded.
Coverage metadata only: Oct20 16:20UTC through Oct22 19:59UTC. Previous consumed
development prices ended Oct22 17:29UTC. Newly acquired raw values have been
saved but no extended features, labels or model outcomes have been inspected.

Run exactly the ten existing v1/v2 models with their already committed rules,
matching, cooldown and delay settings. No refit, search, parameter changes,
model selection, production alerts or independent quality acceptance.

Integrity: check exact native SPX/IND identity, equal raw OHLC array lengths,
aware minute timestamps, chronological uniqueness, finite positive valid OHLC,
completed minutes using min(receipt,provider chart_end), and expected NYSE
calendar coverage. Preserve raw arrays; no fills or invented volume. Compare
all overlapping bars with the prior capture; preserve/report any revisions.

Segments, fixed using timestamps alone:

1. `oct21_reverse_time_transfer`: the full NYSE Oct21 session. It predates the
   consumed Oct22 development session, so it is not forward chronological
   validation; report separately as reverse-time transfer only.
2. `oct22_forward_tail_diagnostic`: Oct22 bars from17:30UTC inclusive to the
   regular close. This is150new minutes after the consumed240-minute prefix.
   Features and candidate cooldown run causally from the Oct22 opening and
   carry into this tail. Only anchors/signals inside this segment are scored;
   first31minutes of session warmup and final10minutes of outcome censoring
   remain unchanged. No reset of cooldown at the tail boundary.

Each segment creates its own fixed event universe from eligible anchors, using
the exact existing ten-minute target max(0.06%close,2priorATR), nonoverlap and
conservative wick-minute25%-target onset. Report all10models on both segments;
strict one-to-one results and0/1/2minute simulated delay stay primary. Preserve
every scored signal/match, misses, Wilson intervals and separate auxiliary
pre-anchor diagnostics. No outcome from one segment changes another's schedule.

Oct20 is partial: inventory/coverage only, excluded from performance. The
previous Oct22 prefix is context/overlap checking only, not new evaluation.
Do not combine the reverse-time segment and forward tail into a claimed
chronological holdout or use the new data to rerank models and claim independence.

The frozen20-session train/validation/holdout protocol is unchanged and cannot
be satisfied by this extension. Status must remain NOT_READY, regardless of
positive point estimates on a small historical segment. No verified live arrival
latency, option quotes, Telegram delivery or trading profit is implied.
