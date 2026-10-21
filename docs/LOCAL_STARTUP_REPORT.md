# Local startup and portability validation — 2026-10-21

This change fixes installation and Windows OAuth persistence. It does not
validate predictive performance or promote any detector beyond **NOT READY**.
The existing historical evidence and artifacts are retained unchanged.

## Source and reproduced failures

The local shallow Git checkout starts at
`c31187222461723cb2a8bc4268fd80e88a960525`. All 243 repository blobs were verified
against their GitHub object identities before editing; the reconstructed tree
and original signed commit also match. Older history is not downloaded.

Environment: Windows, Python 3.12.10. The original NumPy 1.24.3 pin has no
compatible Python 3.12 wheel: `pip install --only-binary=:all: numpy==1.24.3`
fails with "No matching distribution found". NumPy 1.26.4 installs successfully
with the existing pandas 2.1.4 requirement.

An initial full run executed 220 tests: 216 passed, three failed and one errored.
The failures were Windows mode-bit assertions on market journals and OAuth
storage; OAuth reads rejected a file just written by the application because
Windows reports 0666 rather than POSIX 0600. Windows chmod cannot implement
the required access policy. OAuth storage now sets a protected DACL containing
only the current user's full-access ACE, before writing data, and rejects
broader or unprotected file ACLs. POSIX owner-only checks remain in force.

The journal tests retain their data/provenance/deduplication assertions on all
platforms and check POSIX mode bits only on POSIX. Market-only Windows journals
are not claimed to have the OAuth storage's private DACL policy.

The hosted OAuth tests also used a real background thread despite defining an
inline test thread. Running callbacks before that thread initialized state made
the fixture timing-dependent. The fixture now initializes its fake redirect
inline without changing production threading.

## Measured final validation

| Check | Result |
| --- | --- |
| Full unittest discovery on Windows / Python 3.12.10 | 222 passed, 0 failures, 0 errors, 0 skipped; 48.922 seconds |
| Python compilation of application modules and tests | Passed |
| `pip check` in isolated environment | No broken requirements |
| Actual main-process startup and HTTP `/` and `/health` | HTTP 200; process alive, prediction readiness NOT READY |
| Collector/notification state during startup smoke | IBKR disabled, Hunter not started, alerts false; no Telegram credentials |
| Offline OAuth SDK round trip and permission regressions | Passed, including broad-access rejection and failure before token persistence |

The final unittest run blocked non-loopback socket connections (Windows asyncio
needs loopback sockets). OAuth discovery/token HTTP responses came from the
existing `httpx.MockTransport` fixture, not a live broker. Installed versions
included NumPy 1.26.4, pandas 2.1.4, Flask 3.0.0, MCP 1.30.0 and scikit-learn
1.8.0. The HTTP smoke used a temporary database directory and a bounded process
that exited after verification; it did not start collectors or polling.

Reproduce with:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-research.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

CI now covers Linux Python 3.11 and 3.12 plus Windows Python 3.12, using the
full regression suite. A portable compile command avoids shell wildcard
differences. CI results must be checked independently of these local results.

## Remaining operational and research limits

- A long Windows workspace path caused `WinError 206` while installing pywin32.
  An isolated environment under a shorter temporary path solved the local
  installation; the README documents this workaround. No system settings were
  changed.
- No live IBKR authorization, current market-data availability, provider latency
  or production deployment was verified by this change. Runtime OAuth requires
  the application's independent read-only login flow; no credentials were
  requested or exported from connected applications.
- No new holdout study, verified predictive improvement, live SPX option chain
  or executable option recommendation is claimed. Existing research remains
  NOT READY; see the retained historical reports for negative results.
- No paid resources, real-money orders or outbound notifications were enabled.
