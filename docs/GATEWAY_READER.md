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

Experimental strategy events remain shadow-only / NOT_READY. No automatic trade
or SPX option recommendation is enabled. The optional ibapi9.81 diagnostic client
is verified against this Gateway server157; this is not certification against
every modern Gateway/API version. System memory fixes need longer observation.

## GitHub recommendation gate

`github_signal_delivery.py` receives canonical events from the local reader.
It requires READY + notify_eligible + TRIGGER, ES identity, realtime quote
freshness, recent heartbeat/bar/event, complete finite entry zone/stop/targets,
valid directional ordering and a reason. Missing conditions are logged as blocked.
The current unvalidated detector remains NOT_READY and does not manufacture
entry zones/targets, so no recommendation is published from it. A corrected,
validated detector must supply these fields before this gate will publish.

Publishing needs host-side `GITHUB_TOKEN` with issue-write permission. The
interactive GitHub connection is not exported into the host process; no such
local credential was found. A durable per-event reservation prevents duplicates
on the same filesystem, including uncertain network outcomes (manual review is
then required; delivery is deliberately not guaranteed). Preserve the state
directory on restart. Do not delete reservations to force retransmission.

This runs on the signed-in Windows host. A Render instance cannot connect to
this host's127.0.0.1 socket. No cloud deployment or secure tunnel was configured,
and no existing Render service was modified. Gateway transport/reconnect evidence
does not demonstrate a market edge or validate the experimental detector.

Telegram test outcome2026-10-22: local and GitHub Actions both returned
`credentials_unavailable`; no successful message receipt exists. Workflow run:
https://github.com/SuhailAlyami/market-signal-bot-/actions/runs/39718579453
Do not call this a successful alert test. No credentials were copied or exposed.
