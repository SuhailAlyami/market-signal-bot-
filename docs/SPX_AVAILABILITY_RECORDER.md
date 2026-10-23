# Native SPX prospective availability recorder

This closes the missing-observation requirement recorded in SPX_NEXT_HYPOTHESIS_20261023.md. It is a separate read-only process, not another detector. It leaves the existing reader, Gateway settings, Telegram/GitHub paths and research model quota unchanged.

The installer uses the existing research Python runtime and creates only `Suhail SPX Availability`: interactive user, hidden pythonw launcher, at logon and an IgnoreNew 15-minute restart opportunity, no execution time limit. State and original callbacks are outside Git under `%LOCALAPPDATA%/SuhailHunterResearch/availability`. The computer must remain awake/networked with Gateway authenticated; the task does not bypass login or provide cloud hosting. No GUI research app is needed.

```powershell
.\tools\install_spx_availability.ps1
```

Trace protocol was committed before collection in 5d941c5. The process records provider bar starts, exact UTC/local monotonic receipts, changing OHLC versions, initial history versus subsequent updates, and separate price/timestamp callbacks. It never converts initial completed history into prospective availability. A provider mode callback belongs to the parallel SPX quote subscription; it is not a separate bar-mode guarantee. Final OHLC revisions stay explicitly unverified until compared with the one final historical capture. Future feature replay must use the version actually available at decision time, not backdate a final revision.

Before the open it establishes the quote stream, then waits for a current native type1 provider clock before requesting streaming history once. Stale/frozen/pre-open clocks cannot cause repeated empty history requests. Sessions follow NYSE holidays, DST and early closes. Disconnections/gaps are recorded, reconnects back off, and an explicit request rejection stops unchanged retries for that session. Process and scheduler locks avoid duplicate writers.

Full-session publication requires every expected minute, prospective start, mode1 observations, and no missing/corrupt log. Once the session is full and closed, obtain final daily history once (or reuse an existing hashed native capture); rejected/incomplete captures remain incomplete. Only a complete trace plus complete final native history publishes a new ignored `.hunter-state/spx-availability/<day>/raw.json` to the installed research worktree. Partial days do not wake its model. The resulting session is availability diagnostic DEVELOPMENT, not untouched directional validation. No alerts or strategy promotion follow automatically.

Smoke evidence in `artifacts/spx_availability_smoke_20261023/evidence.json` contains real callbacks. Ten targeted offline checks passed: backfill exclusion, snapshot/receipt retention, gap/mode/partial rejection, reconnect timing, separate quote callbacks, resume integrity, calendar/DST, hashed daily reuse/no overwrite, tampered-input rejection, and one-time live-open history startup. These tests are not market-quality evidence.

The current Friday October23 capture started mid-session and remains partial. The next possible complete session is Monday October26, **16:30–23:00 Asia/Riyadh**, followed by the five-minute close grace period. This is a data requirement, not a guarantee: missed minutes, sleep, missing permissions or Gateway login interruptions leave the session incomplete. Preserve the existing two-model-calls/day limit; do not retune old samples while waiting.

Pause this observer only: create `STOP` in its private availability state folder. Remove that marker to allow the next scheduled restart. Do not remove raw files or holdout registries. Inspect `status.json` and `events.jsonl` locally; do not upload original private logs. Source API semantics: [IBKR historical bars](https://www.interactivebrokers.com/docs/tws-api/doc/md/historical-bars), [keepUpToDate callbacks](https://interactivebrokers.github.io/tws-api/historical_bars.html).
