# Local Gateway daily acquisition check ? 2026-10-23

Scope frozen before acquisition: transport and data integrity only. No detector
hypothesis, parameter selection, event scoring, validation or holdout opening.
Existing negative consensus/lifecycle results remain NOT_READY.

Endpoint: 127.0.0.1:4001, from collect_spx_sessions.py and
 docs/SPX_HISTORY_COLLECTION.md. A TCP-only connection succeeded at
2026-10-23T12:17:15.258520+00:00; this does not identify the listener or establish
API access, entitlement, REALTIME/FROZEN/DELAYED status or actual live latency.
Python ibapi, pandas and pandas_market_calendars are available.

Bounded acquisition: existing unmodified collect_spx_sessions.py, one NYSE session
ending 2026-10-19, SPX/IND/CBOE/USD, one-minute TRADES, useRTH=1. This is outside
the consumed Oct20?22 samples. Native API contract resolution must identify a
unique SPX contract. Request only contract details and daily historical data;
no account, position, order or credential requests. No source substitution.
One request attempt, existing timeout, no retry. Raw output stays private under
.hunter-state/spx-gateway-check-20261023-oct19/capture and is never staged.

Integrity gate: all 390 expected NYSE minutes, finite consistent OHLC, ordered
provider timestamps and no conflicting duplicates. Preserve raw provider bars,
provider bounds, receipt time and hashes. Receipt is batch receipt, bar timestamp
is provider bar start, hypothetical completed-bar decision is start+60 seconds;
none is an exchange arrival timestamp or executable trade time. Historical TRADES
is a request field, not evidence of live market-data mode or individual trades.
Market-data mode remains UNKNOWN. Reject partial capture for research eligibility.

No model gate can pass in this check. One session cannot support independent
12/4/4 chronological evidence. No outcomes will be computed even if collection
succeeds. Any later outcome inspection requires a committed prospective protocol
and exclusion of all consumed dates appropriate to that hypothesis. Oct23 is not
complete at check time (NYSE open 13:30 UTC, close 20:00 UTC).

Command (new directory only):
```powershell
python collect_spx_sessions.py --end 2026-10-19 --sessions 1 --output .hunter-state/spx-gateway-check-20261023-oct19/capture --port 4001
```

Next eligible forward capture, only after 2026-10-23T20:00:00Z:
```powershell
python collect_spx_sessions.py --end 2026-10-23 --sessions 1 --output .hunter-state/spx-forward-20261023/capture --port 4001
```
This is collection only; do not run the older evaluator on forward dates (it
explicitly excludes dates on/after Oct22). No options, alerts or production edits.

## Measured result

TCP connection succeeded; API handshake and daily collection were NOT run.
Before acquisition, both explicit git add and commit failed: linked-worktree
Git metadata is outside the writable workspace; index.lock creation returned
Permission denied. No lock was deleted and no Git metadata was changed manually.
Four existing synthetic collector tests passed (3.148s); their printed 390/390
rows are mocked data, not an actual capture. No new independent market evidence.
Status BLOCKED for local recovery; model quality remains NOT_READY.
No push was attempted because no new commit could be created.
