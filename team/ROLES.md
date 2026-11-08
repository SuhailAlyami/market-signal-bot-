# Roles (used per cycle; agents are spawned only with a concrete task)

| Role | Who | Responsibility |
|---|---|---|
| Lead / engineer | main Claude session | Reproduce latest test, diagnose, preregister one change, implement, run, document, PR |
| Independent reviewer | read-only subagent | Audit leakage, timezones, execution sim, metric code, and that README numbers match summary.json |
| Owner | Suhail | Logins, paid services, secrets, merge decisions |

Reviewers never edit the repo; their findings are copied into the experiment README with file:line evidence.
