# Hosted read-only IBKR setup

The Flask service now provides `/ibkr/setup`, protected by an owner setup key.
It starts a bounded OAuth/PKCE flow using the existing MCP SDK. The browser
logs in directly at IBKR; no broker password is entered into this app.

Configure these **service environment variables**, never repository files:

- `IBKR_WEB_ORIGIN`: the exact HTTPS origin of the service, without a path.
- `IBKR_WEB_SETUP_KEY`: an independently generated random secret of at least
  32 characters. Retrieve it privately from Render's Environment page.
- Existing `IBKR_MCP_AUTH_DIR` may select private storage outside the checkout.

Open `/ibkr/setup`, paste the owner setup key from Render, then follow the
IBKR sign-in link. The form requires the same Origin, and the callback requires
the short-lived secure HttpOnly browser cookie plus the single-use OAuth state.
Only `mcp.read` may appear in the outbound authorization request. Broader scopes,
foreign redirect destinations, untrusted authorization hosts, missing cookies,
replayed callbacks, and expired sessions are rejected. No market/account query
or Telegram send occurs as a side effect of authorizing.

The existing workers retry on their next polling cycle. An `authorized` setup
status does **not** establish live market entitlement, fresh ES/NQ history,
detector quality, or delivery. Verify `/health` and structured worker logs after
sign-in. The NY regular-session consumer in `spx-agent` is a separate service;
this change does not switch it to Render or duplicate its alerts.

## Remaining limitations

- Render Free sleeps without incoming traffic. This is not an always-on service.
- Existing private filesystem token storage is ephemeral on Render Free.
  Container replacement/redeployment can require reauthorization. No broker
  tokens are copied into environment variables, GitHub, reports, or logs.
- Keep the setup key private. A holder can initiate replacement of this runtime's
  broker session; the key is not an IBKR password. Rotate it in Render if exposed.
- Web setup must run in the existing single-process, single-instance deployment;
  in-memory browser state is not shared across processes or instances.
- No new paid resources, persistent datastore, or trading permissions are added.
- Broker-side consent and end-to-end live tests require the owner. Unit tests
  and successful deployment are not proof that the market connection works.

The prior loopback-only authorization remains available for local installations.
