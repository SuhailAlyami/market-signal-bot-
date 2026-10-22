# Required final state: independent of the owner's computer

User requirement recorded2026-10-22: finish current ES realtime monitoring and
GitHub/Telegram conditional alerts first; then explain requirements/costs before
creating any paid service. No trades, account operations or subscription purchase.

Current deployment is NOT independent: Render evaluates signed data, but the
Windows Gateway, data reader and notification publisher still run on the owner's
computer. Turning it off stops the feed and publisher. Render's paid tier alone
does not move IB Gateway or its authenticated session off that computer.

A concrete proposed independent deployment (not provisioned):

- One Linux x86 VPS, initially budgeted with8GB RAM to avoid repeating native
  Java memory pressure, with Gateway, existing reader and sender colocated.
- IBKR/Derayah account login and necessary2FA on that host through protected
  remote GUI; API stays read-only and bound to localhost. Verify existing ES
  entitlement on the new session; do not buy subscriptions automatically.
- Service supervision, automatic reconnect, persistent journal/dedupe/receipts,
  disk retention, timezone-aware clock and outage/credential-expiry monitoring.
- GitHub authenticated identity with issue-write access, Telegram encrypted or
  host-managed secrets, and migration of delivery reservations to avoid duplicate
  sends. Current Windows DPAPI blobs cannot just be copied to Linux: secrets must
  be entered securely into the chosen new host secret store.
- Keep existing free Render for UI/health if desired, or run existing Flask app
  on the VPS behind HTTPS. No extra paid database is necessary for this scope.

Indicative cost checked2026-10-22, not an order or guaranteed quote:
Hetzner's June2026 official EU table lists CX33 at8.49EUR/month or9.99USD/month,
excluding IPv4 and VAT. Allow approximately10–15EUR/month total as a planning
estimate including optional networking/backups/tax uncertainty; final regional
availability, hardware/RAM and checkout total must be verified before approval.
No new market-data fee is assumed or authorized; entitlements must be checked.

Pricing source: https://docs.hetzner.com/general/infrastructure-and-availability/price-adjustment/

Independent hosting does not mean permanently unattended broker authentication.
IBKR documents weekly manual reauthentication and possible earlier token
revocation. Owner2FA remains necessary; do not promise to bypass it.
https://www.ibkrguides.com/traderworkstation/auto-restart-considerations.htm

No VPS, paid Render tier, paid backup or market subscription has been created.
