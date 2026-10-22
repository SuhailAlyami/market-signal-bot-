# Isolated removal audit ? 2026-10-22

Removed only auto_auditor.py and the byte-identical .github/auto_audit.yml plus
.github/workflows/.github/workflows/auto_audit.yml. The script sends all Python
source to Groq and overwrites files; neither YAML is a recognized top-level
.github/workflows/*.yml entry. They reference only each other and the inventory
row updated here. No production imports, tests, recognized workflow, Render
command or requirements install invokes them. requests remains required elsewhere.

Inspected Python imports, CLI/document references and exact SHA256 duplicates.
Retained all requirements: no package was proved exclusively needed by removed
files. Retained historical scanners/evaluators and archived state duplicates,
including cboe_delayed_research.py (unreferenced does not prove research worthless),
AGENTS.md, deployment files, tests, reports and important evidence. No branches,
unmerged work or Git history were deleted.

Validation: removal reference audit; no runtime/dependency behavior changes, so
no rerun of previously passing application suites is needed. This isolated branch
does not edit or restart the running reader or cloud service.
