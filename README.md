# Suhail Hunter — NOT READY

> **Active Telegram path:** [SuhailAlyami/spx-agent](https://github.com/SuhailAlyami/spx-agent).
> The legacy `ibkr_session.yml` here is manual readiness/research only. It has
> no automatic schedule or push trigger. Missing `IBKR_RUNNER` is reported as
> `COLLECTOR_NOT_CONFIGURED`, not successful market detection. A session requires
> a configured host and explicit `start_session` input; alerts remain off here.
> This change does not activate minute-level data collection.

Research-only early directional WATCH for ES/NQ underlying bars. No verified
predictive edge, live SPX option chain, option quotes, fills, or real-money orders.
Experimental alerts are OFF. Passing CI and HTTP uptime do not establish
prediction quality.

Issue #16 evidence and measured holdout results: [engineering report](docs/ISSUE16_REPORT.md).
See [scanner inventory](docs/HUNTER_INVENTORY.md), [data-source review](docs/DATA_SOURCES.md),
and the governing [AGENTS.md](AGENTS.md).

أرشيف شموع الدقيقة المجاني وشرح IBKR المحلي: [data/archive/README.md](data/archive/README.md). على جهازك مع TWS أو IB Gateway مفتوح، بلا اشتراك لحظي:

```bash
python archive_1m.py --source ibkr --backfill-days 180 --use-rth 1 --port 7496
```

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Python 3.11 and 3.12 are supported. NumPy 1.26.4 provides wheels for both;
the former 1.24.3 pin had no Python 3.12 wheel. CI runs the deterministic
regression suite on both Python versions, plus Windows on Python 3.12.

On Windows PowerShell, run from the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-research.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

If installation reports `WinError 206`, create the virtual environment in a
shorter writable path (for example under `$env:TEMP`) and use its Python
executable for the same commands. Gunicorn is the Linux deployment server;
use `python market_signal_bot.py` for local Windows startup.

OAuth storage uses a protected DACL granting access only to the current user on
Windows, and owner-only permissions on POSIX. It remains outside the checkout.
The Windows ACL implementation uses pywin32, installed by the MCP SDK, and
rejects storage with broader access. Market-only journal mode-bit checks apply
on POSIX; those bits do not represent Windows permissions.
Runtime state and the Arabic shadow journal use explicit UTF-8 on every host,
including Windows machines whose default text encoding is a legacy code page.

For a local HTTP-only startup check with all collectors and Telegram disabled:

```powershell
$env:IBKR_MCP_ENABLED = 'false'
$env:GLOBEX_RENDER_ENABLED = 'false'
$env:ENABLE_TELEGRAM_POLLING = 'false'
$env:TELEGRAM_BOT_TOKEN = ''
$env:TELEGRAM_CHAT_ID = ''
.\.venv\Scripts\python.exe market_signal_bot.py
```

Open `/health` on port 8080. Process liveness does not verify market data or
prediction quality. Restart with the collector settings you intend to use;
an authorized independent IBKR session is still required for market data.

The canonical runtime is `hunter_runtime.py`, shared by `cloud_scan.py` and
`globex_render_worker.py`. It validates completed 1m candles, rejects stale or
invalid data, persists lifecycle/dedupe state, and appends observations, heartbeat
and subsequent underlying outcomes. Arabic states are استعداد / دخول مشروط /
إلغاء / خروج; all refer to research observations of the underlying.

```sh
python globex_render_worker.py --once --state-dir .hunter-state
python market_signal_bot.py
```

A one-shot run exits nonzero for stale/unavailable data and saves the reason in
its shadow journal. `/health` distinguishes process liveness from worker/feed
health and exposes the last completed bar and heartbeat age. Telegram credentials
are optional; no experimental market notifications are sent. Legacy Asia/US/FVG
scanners are archived for comparison and are not launched by the main process.

`HUNTER_CHECK_SECONDS` defaults to 60 (minimum 60); `HUNTER_STATE_DIR` defaults to
`.hunter-state`. Run one process against each state directory. Local atomic JSON
survives process restart on a retained filesystem. Render free replacement can
erase it; Actions cache and scheduling are best effort. No durable-storage or
low-latency guarantee is claimed. No paid resource is provisioned.

Reproduce the retained historical study without making any provider request:

```sh
pip install -r artifacts/issue16/requirements-research.txt
python hunter_research.py --input artifacts/issue16/data/es_1m.csv.gz --symbol ES=F --session both --output-dir /tmp/hunter-es --as-of 2026-10-19T09:00:51.641639Z
python hunter_research.py --input artifacts/issue16/data/nq_1m.csv.gz --symbol NQ=F --session both --output-dir /tmp/hunter-nq --as-of 2026-10-19T09:00:51.641639Z
```

This uses chronological train/validation/untouched holdout partitions, train-only
walk-forward parameter search, horizon embargo, event matching, baselines and
delay sensitivity. Historical snapshots can be revised by their provider; their
original hashes and acquisition metadata are retained. Research returns no
execution P&L and cannot show that SPX premiums were still available.

Optional bounded free acquisition, saved separately from the published snapshot:

```sh
python acquire_hunter_data.py --output /tmp/new-hunter-data --weeks 4
python acquire_hunter_data.py --output /tmp/new-hunter-probes --probe
```

Yahoo/CME futures data is delayed; measured latest-bar age is not provider
publication latency. The runtime rejects the roughly ten-minute-old observations
rather than relabeling them live. Read the report before interpreting any metric.
