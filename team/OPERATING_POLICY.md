# Operating policy (2026-11-08)

- Language: English for internal instructions, agent messages, code comments, logs, technical docs. Owner-facing decisions, blockers and final summaries in concise Arabic. Do not duplicate documents across languages.
- Skills: project has no local skills (`.claude/skills` absent) and none is needed now. Add one only for an identified need, after inspecting its instructions, scripts, dependencies, license and network behavior; reject secret exfiltration, untrusted commands, paid services; pin the source revision and record the inspection in `team/SKILLS_LOG.md`. Nothing installed so far.
- Efficiency: calculations, validation, replay and metrics live in reusable Python scripts, not model arithmetic. Keep CLAUDE.md short; detail goes in team/ or experiment READMEs.
- Cost: choose the least costly adequate model; no paid overages or paid external APIs.
- Usage telemetry (fields as actually reported; never invented): subagent completion notices give one `subagent_tokens` total, tool calls and duration. Input / cached-input / output split, billing and allowance metrics: NOT reported (unavailable). Main-session usage: unavailable. No savings percentage is claimed.
  Both reviewer figures are from the earlier 2026-11-08 runs (not rerun): methodology reviewer 104,062 tokens / 10 tool calls / 136 s; opening-seed reviewer 86,976 / 8 / 60 s. No agent ran in this data-acquisition step.
