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
