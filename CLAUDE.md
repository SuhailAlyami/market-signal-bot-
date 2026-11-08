# CLAUDE.md — Suhail Hunter

Read `AGENTS.md` (governing mission) and `RESUME.md` (current state; check its date against branches/PRs) first.

## Non-negotiables
- Status is NOT_READY / RESEARCH_ONLY until an untouched-holdout result beats baseline. Alerts stay OFF. No real orders.
- Never invent prices, option quotes, strikes, fills, confidence numbers or test results.
- Label every data source LIVE_VERIFIED / DELAYED / RESEARCH_ONLY with the reason; keep market time, receipt time and request time separate.
- The 116 sessions 2026-05-19..2026-11-04 are consumed. Never call results on them "out-of-sample".

## Research protocol
- One change per experiment. Commit `protocol.json` (hypothesis, metric, decision rule) BEFORE computing results; push it.
- Report against an unchanged control rerun in the same script. Keep failures; never retune after seeing results.
- Measure detection (early recall, lag vs onset, false alarms/session, misses) separately from execution P&L.
- Put each experiment in its own folder with code, tests, protocol, summary.json, results, README_AR.md and MANIFEST.json.

## Environment
- Research deps: `research/objective_review_20261107/requirements.txt` (exchange_calendars). App tests: `python -m unittest discover -s tests` after installing requirements*.txt.
- Work on a feature branch; open PRs, do not merge to main without the owner.

See `team/` for roles and delivery rules.
