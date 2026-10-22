# Local Gateway feed for Suhail Hunter

This reuses `HunterRuntime`; it does not add another detector. It runs ES only,
with native 1-minute historical updates and a separate realtime quote subscription.
The nearest unexpired ES contract is selected by expiry, not a liquidity roll.

Install `requirements.txt` and `requirements-gateway.txt` in the local environment.
Run `python gateway_hunter.py` with Gateway signed in, Read-Only API enabled,
localhost port4001. Default duration is continuous; `--seconds 190` bounds a run.
`--reconnect-test-after 65` disconnects only this reader once to test recovery;
never use it in routine monitoring. `--test-alert` sends one explicit TEST only
when the runtime is healthy and Telegram credentials already exist in environment.
The test receipt persists to prevent another successful test on restart.

Quote entitlement must be type1, latest trade and quote receipt <=60seconds old.
Completed bars still pass the canonical chronology, gap, volume and freshness
checks. A stale/delayed/disconnected feed fails closed. Connection errors and
changes in runtime health are journaled, then subscriptions are rebuilt with
exponential retry delay capped at60seconds. Do not repeatedly launch readers:
an OS lock protects each state directory, and a fixed client ID identifies this
one local monitoring process.
Gateway login/2FA still requires the account owner; retries cannot bypass it.

Files under `.hunter-state/gateway/`:

- `heartbeat.json`: current receipt, quote type, session/tick counts and canonical
  runtime heartbeat including last completed bar.
- `connection.jsonl`: observed samples, disconnects, attempts, recovery and stop.
- `shadow.jsonl` / `state.json`: existing detector research log and dedupe state.
- `spx-probe.json`: bounded contract/quote permission observations, not a live cache.

`gateway_spx_probe.py` requests SPX/CBOE, option chain metadata and two resolved
SPXW call/put contracts near an observed index last/close. It buys no subscription
and sends no account/order requests. A type1 callback is entitlement evidence,
not proof a closed-market last trade is current. Bid/ask callbacks record local
receipt time, not independently verified exchange quote timestamps.

The explicit GitHub Actions Telegram test uses existing repository secrets and
the sanitized recorded validation evidence. It tests the same message sender
through a manual CI relay; it does not install those credentials locally or
prove unattended local Telegram delivery. API acceptance/message_id is delivery
to Telegram, not proof that a person read the message.

Canonical strategy events remain research-only / NOT_READY. Explicitly authorized
experimental ES rule alerts can be enabled with `--github-signals`; this is not
evidence of a statistical edge. No automatic trade or SPX option recommendation
is enabled. The optional ibapi9.81 diagnostic client
is verified against this Gateway server157; this is not certification against
every modern Gateway/API version. System memory fixes need longer observation.

## GitHub recommendation gate

`github_signal_delivery.py` receives canonical events from the local reader.
It requires COMPLETE + notify_eligible + TRIGGER, ES identity, realtime quote
freshness, recent heartbeat/bar/event, complete finite entry zone/stop/targets,
valid directional ordering and a reason. Missing conditions are logged as blocked.
`es_signal_plan.py` fills the missing causal ES plan after the existing two-close
confirmation, rechecks relative volume>=1.2 and compatible5/15min trends, and
requires a directional confirming candle. Entry is close±0.05ATR rounded to ES
0.25ticks, stop is the original invalidation rounded outward, maximum risk2ATR,
targets1R/2R. A current last price outside that entry zone blocks sending.
The detector's unvalidated research status is preserved and stated in each issue.

Publishing uses host-side `GITHUB_TOKEN` or the official GitHub CLI's approved
browser login, without exporting connector credentials or printing OAuth tokens.
A durable per-event reservation (ES/direction/bar/rule identity) prevents duplicates
on the same filesystem, including uncertain network outcomes (manual review is
then required; delivery is deliberately not guaranteed). Preserve the state
directory on restart. Do not delete reservations to force retransmission.

The Windows reader can push signed market-data-only HTTPS requests to the
existing Render `/gateway/ingest` route with `--relay-config` pointing to its
private generated configuration outside the repository. The server validates
HMAC, request age, replay nonce, ES contract identity and quote freshness before
running the same HunterRuntime. It returns complete candidate plans; the Windows
publisher rechecks freshness and current entry eligibility before creating issues.
No IB socket or account/order API is exposed. A failed cloud relay does not fall
back to publishing local detector events. Relay credentials use current-user
DACLs on Windows and Render secret environment variables, never source control.
The matching existing service is `srv-da44n0qjobas73a9cen0`, repo same as this PR.
`GATEWAY_RELAY_ENABLED=true` selects this path and stops competing MCP collectors.
Health changes to gateway_relay_stale after30seconds without a fresh ingest.
The free host may sleep, lose dedupe state or restart: the Windows durable issue
reservations remain authoritative. Signed-in Windows/Gateway must stay running.

Telegram test outcome2026-10-22: local and GitHub Actions both returned
`credentials_unavailable`; no successful message receipt exists. Workflow run:
https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/39718579453
Do not call this a successful alert test. No credentials were copied or exposed.

## Current Telegram setup (2026-10-22)

`--telegram-signals` independently delivers the same strictly gated ES plans.
`secure_telegram_setup.py` opens a local masked token form. Credentials are
encrypted with Windows current-user DPAPI and protected DACLs outside the repo
at `~/.local/share/suhail-hunter/telegram/credentials.dpapi`. They are reloaded
without restarting the reader, and never copied into source or the cloud relay.
Start the bot conversation before saving its chat ID. No credential is entered
through chat. Existing environment/project config/Credential Manager searches
found no usable pair; Render connector does not expose an environment-read tool.

With healthy data, exactly one explicitly labelled transport verification is
attempted after credentials become available. Its durable reservation/receipt is
`.hunter-state/gateway/telegram-delivery/verification.json`. Even an uncertain
network outcome is not automatically retried. Telegram API acceptance/message ID
is evidence of server delivery, not human reading. Until a receipt exists,
Telegram delivery is unverified. Missing/invalid Telegram credentials do not
disable GitHub. Both channels have independent per-event dedupe and shared
freshness/complete-plan gates. Research remains unvalidated; no trades.

The required independent-host target and indicative cost are documented in
`docs/INDEPENDENT_OPERATION.md`; no paid resource has been provisioned.
