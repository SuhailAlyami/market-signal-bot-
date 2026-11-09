# SPX 1m bar collector (Yahoo ^GSPC) — research data only

No alerts, orders, secrets or paid services. Data class: **DELAYED_RESEARCH_ONLY** (Yahoo declares no delay or contract identity; historical bars carry no per-bar receipt time, only the snapshot's `requested_at`/`received_at`/`regularMarketTime`).

## What it does
`collect_yahoo_spx.py` fetches `range=7d, interval=1m`, drops null/invalid and still-forming bars, keeps only complete XNYS regular sessions (09:30..close-1m, early closes and DST from the calendar), never fills gaps, and stores:
- `raw/<UTC stamp>_GSPC_1m.json.gz` — raw response, created exclusively (never overwritten);
- `snapshots.jsonl` — one line per stored snapshot (times, status, market state at receipt, last completed bar and its age, raw sha256);
- `sessions.json` — complete sessions in the `opening_validation_raw` schema; the first complete read is canonical, later differences are logged, not applied.

An identical provider payload (same sha256) is skipped (`DUPLICATE_PAYLOAD_SKIPPED`); provider/network errors exit non-zero and are recorded. `--verify` audits stored sessions against the calendar with no network. `market_status()` classifies a timestamp as PRE_OPEN / OPEN / POST_CLOSE, or NO_SESSION with reason WEEKEND or HOLIDAY, with Asia/Riyadh times.

## Workflow `.github/workflows/spx_collect.yml`
- `pull_request` (paths above only): runs the tests (`contents: read`). `schedule` / `workflow_dispatch`: tests, then collect.
- Schedule `45 21 * * 1-5` UTC = **00:45 Asia/Riyadh (Tue–Sat)**: 45 min after the NYSE close in winter (21:00 UTC = 00:00 Riyadh), 1 h 45 min in summer. Best effort; GitHub may delay it. Yahoo keeps 7 trading days, so a missed run is recoverable for about a week.
- Data lives on the existing branch `data/spx-collection` (dispatch input `data_branch`, must start with `data/`), never on `main`. Authenticated checkout of that branch only; the code checkout does not persist credentials; job permission `contents: write` only for the collect job.
- One writer at a time (`concurrency: spx-collect-data`, no cancel); push is fast-forward only, no force; a rejected push fails the run visibly. After pushing, the job checks the remote ref equals the local HEAD and then runs `--verify` (red on any calendar gap).
- Nothing is pushed when there is nothing new.

## Run locally
```
pip install -r requirements.txt
python -m unittest test_collect
python collect_yahoo_spx.py --out /path/to/data
python collect_yahoo_spx.py --out /path/to/data --verify
```
