# Suhail Hunter — NOT READY

Research-only early directional WATCH for ES/NQ underlying bars. No verified
predictive edge, live SPX option chain, option quotes, fills, or real-money orders.
Experimental alerts are OFF. Passing CI and HTTP uptime do not establish
prediction quality.

Issue #16 evidence and measured holdout results: [engineering report](docs/ISSUE16_REPORT.md).
See [scanner inventory](docs/HUNTER_INVENTORY.md), [data-source review](docs/DATA_SOURCES.md),
and the governing [AGENTS.md](AGENTS.md).

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
```

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
