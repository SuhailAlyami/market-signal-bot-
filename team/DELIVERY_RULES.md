# Delivery rules and corrections log

## Delivery
- Arabic short report: what ran, before/after metrics with sample size, tests run, branch/PR link, evidence paths, what is unproven.
- No claims of continuous/background operation unless started and verified in that cycle.

## Corrections log
- 2026-11-08: RESUME.md (2026-10-24) was stale vs open PRs #51/#53; always compare RESUME date with branches/PRs.
- 2026-11-08: wave_capture `end < 7` undercounts warm-up misses (should be `end <= 7`); 2026-09-11 missing from 116-session input and unreported. Documented in opening_seed/README_AR.md; original files unchanged.
- 2026-11-08: opening_seed test expectation initially wrong (decision time is bar1 close = open+10m); test fixed, code unchanged.
