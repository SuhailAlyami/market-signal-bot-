# SPX silence diagnosis — 2026-10-24

This is an operational/consumed-data diagnostic, not a new hypothesis or independent market validation. Source baseline: 188424f7b683f33772984adf7aed906c9db393bb (PR45). Saturday: no market-data or brokerage calls were made.

## Verified cause and limits

spx_primary.run explicitly sets notifications_enabled=False and journals research events. spx_price_watch.observe and HunterRuntime events set notify_eligible=False / NOT_READY. Existing send switches do not enable SPX price-watch delivery. Thus no Telegram message does not imply no internal candidate. This source inspection cannot establish whether the owner's local process was running during a particular missed market movement.

The observer/reader research work is not a validated detector. No flags, thresholds, subscriptions, options, secrets, orders, production branch, or sender were enabled/changed.

## Change

SPXPriceRuntime now journals one candidate_disposition for each newly processed bar, distinguishing no_candidate, setup_created, active_setup, active_trigger and cooldown. It retains the actual causal candidate, decision and bar times, transition states, and explicit research_notifications_disabled blocker. Durable bar dedupe still excludes repeated polling. The replay includes the same evidence and aggregate counts. These records explain silence; they do not bypass quality controls.

## Measured consumed-data replay

Input artifacts/spx_extension_20261023/raw.json, 1000 native-SPX minute bars spanning partial Oct20 through Oct22. Historical replay assumes decisions at nominal minute end; actual per-bar availability is unverified. No claim of live early prediction or option P&L.

967 RTH processed decisions after warm-up: no_candidate573, setup_created144, active_setup53, active_trigger139, cooldown58. 394 raw candidates;250 did not create a new setup. These suppressions are not automatically bugs: an existing scenario or cooldown can intentionally suppress repeats.

Scorable WATCH140 /63movement events;precision28.57%;6early matches;medianlead-1minute;false33.33 per full-session equivalent. Confirmation87;precision27.59%;4early;medianlead-1minute;false21.0. Four setups are censored by outcome eligibility. These are consumed overlapping-event diagnostic measures, not independent validated trading statistics.

Exact comparison to the prior runtime on the same input preserved metrics, every WATCH, every confirmation and movement event. Therefore predictive quality did NOT improve in this patch. No failed family is promoted.

## Verification and next work

15 targeted tests passed (candidate disposition, existing SPX lifecycle and price-watch tests). Two new tests distinguish candidate suppression/dedupe and no-candidate/cooldown without delivery. Exact prior-runtime replay equivalence passed. Full machine reader/Windows delivery not tested from this environment.

Replay: python replay_spx_price_watch.py --input artifacts/spx_extension_20261023/raw.json --output NEW_PATH.json --protocol-commit 188424f7b683f33772984adf7aed906c9db393bb

All July20-Aug14 and Oct20-Oct22 outcomes remain consumed development. Preserve prospective availability recording; do not label history receipt as live latency. Use a separately preregistered hypothesis and genuinely uninspected data for the next quality experiment; retain NOT_READY. Installing this research patch on the owner's Windows process is separate from saving it to GitHub; no local installation is claimed.
