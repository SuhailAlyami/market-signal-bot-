# Operational readiness before an opportunity

The system must distinguish four facts: code passed tests, an authorized
collector is running, market inputs are fresh, and a detector has demonstrated
an edge. None implies the others. The present detector remains NOT READY on
quality; there is no reliable early-options claim.

## Silent-skip defect repaired

The scheduled NY workflow previously skipped its only job when IBKR_RUNNER was
unset. A successful/empty workflow could therefore coexist with no detection.
It now runs a hosted configuration job first, retains a JSON readiness artifact
and fails visibly with COLLECTOR_NOT_CONFIGURED when the runner is absent.
Configuration presence only yields HOST_CHECK_REQUIRED, never a live-data claim.
Publication triggers the configuration job without launching a duplicate collector.
The scheduled NY job still starts at 13:25 UTC, before both summer/winter opens.

The hosted diagnostic is now manual-only: rechecking an unauthenticated ephemeral
machine every five minutes cannot acquire data and wastes free Actions time.
The continuous workflow retains its daily session schedule.
Both continuous and manual diagnostic workflows now require same-host runtime
IBKR authorization and fail clearly when it is absent. Authorization is not a
market-data test; subsequent consumers retain independent realtime/freshness
checks. Missing authorization never triggers an implicit login, account query,
Yahoo fallback or order.

An unexpected cycle exception previously could terminate the collector without
a new session heartbeat. It now writes RUNTIME_ERROR, error TYPE only and the
attempt time atomically, then retries at the existing bounded cadence. Once
mode and an exhausted runtime ending in this state exit nonzero. Persistence
failures still terminate rather than claim health. Provider exception messages
are not exported because they can contain authentication data.

## Same-host liveness check

```bash
python session_health.py --heartbeat ~/.local/state/suhail-hunter/ibkr-session/session-heartbeat.json
```

During the actual NY session, missing/malformed, future or >180-second-old
heartbeats fail. A recent OBSERVED cycle requires both consumers' success
markers. Outside the session this command reports the closed/waiting calendar
state and never marks a collector active. It separates collector operation
from detector quality, which remains NOT_READY. It is a local inspection
command, not an independently hosted dead-man monitor or notification service.
A stopped machine cannot report its own failure; external scheduling/delivery
must be separately verified before claiming unattended fault coverage.

## Current material blocker

A real previous GitHub configuration run reported IBKR_RUNNER missing.
Chat-connected IBKR can be read, but this does not authenticate a GitHub-hosted
process. No authorized always-on runtime has been proven. This change makes
that state visible; it does not provision a host, transfer OAuth, establish
continuous capture or certify option quotes. ChatGPT's hourly review task is
separate and can miss fast moves. No paid service or Render dependency is added.

Before declaring live readiness, retain evidence of an actual collector start,
completed realtime ES/NQ cycles, new first-receipt journals, restart recovery,
a failure/recovery rehearsal, and separately timestamp-verified SPX option
books for any contract suggestion. No historical signal can substitute for
these checks. A successful readiness check still cannot promise detection of
every price expansion or a profitable option trade.
