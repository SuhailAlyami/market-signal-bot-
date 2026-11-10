# Roles (coordinator = main session; specialists only for concrete tasks with defined outputs)

| Role | Output | Default |
|---|---|---|
| Research/data | data validation, protocol.json, metrics scripts | coordinator, or one worker |
| Engineering | code + tests + replay scripts | one worker, cheapest adequate model |
| Independent validation | read-only audit: leakage, timezones, execution sim, README-vs-summary check | one reviewer, stronger model for hard reasoning |
| Delivery/documentation | README, RESUME.md, PR, Arabic owner report | coordinator |

Rules: no idle or duplicate agents; pass only relevant files and concise context; agents return summaries plus evidence paths;
reviewers never edit the repo; reuse verified results when code and inputs are unchanged.
