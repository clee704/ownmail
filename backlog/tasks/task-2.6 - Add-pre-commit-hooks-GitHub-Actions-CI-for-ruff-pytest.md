---
id: TASK-2.6
title: Add pre-commit hooks + GitHub Actions CI for ruff/pytest
status: Done
assignee: []
created_date: '2026-07-24 04:43'
updated_date: '2026-09-22 17:25'
labels: []
milestone: m-2
dependencies:
  - TASK-4
parent_task_id: TASK-2
priority: low
ordinal: 7
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
ownmail documents 'run ruff check && pytest' in CONTRIBUTING.md but has no automated enforcement (no .pre-commit-config.yaml, no .github/workflows/ci.yml) — wiring the equivalent checks into pre-commit + CI is what stops agents forgetting to run them. Add a .pre-commit-config.yaml (ruff check, ruff format --check, pytest + coverage gate; consider deptry for unused deps) and a GitHub Actions workflow running the same checks on push/PR. Skip vulture/import-linter — those answer a plugin/seam architecture ownmail doesn't have.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 pre-commit run -a passes locally with ruff + pytest hooks wired
- [x] #2 GitHub Actions workflow runs the same checks on PRs
- [ ] #3 Superseded by #4 after TASK-4 raised the floor to 3.10: GitHub Actions CI runs the test suite on a matrix of all Python versions in pyproject.toml's classifiers (3.8, 3.9, 3.10, 3.11, 3.12)
- [x] #4 Matrix updated to 3.10, 3.11, 3.12 once TASK-4 lands (not 3.8/3.9 - both past upstream EOL)
- [x] #5 ruff check passes clean repo-wide (fix the ~171 pyupgrade/UP findings surfaced by TASK-4's py310 target-version bump, e.g. PEP 604 X | Y unions, before wiring the hook that would otherwise fail on them)
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Local dev/test runs were observed on Python 3.14, outside the previously-declared 3.8-3.12 support range in pyproject.toml classifiers. Per TASK-4, the floor is being raised to 3.10 (3.8/3.9 are past upstream EOL), so the CI matrix should target 3.10-3.12, not the original 3.8-3.12 range.

**Ledger repair, 2026-09-22 (TASK-42).** Removed five number-only accidental criteria. #3 is superseded by #4: CI runs Python 3.10, 3.11, and 3.12, matching the classifiers after TASK-4. The remaining criteria are met by .pre-commit-config.yaml, .github/workflows/ci.yml, and a clean ruff run; CI first ran remotely in TASK-42.
<!-- SECTION:NOTES:END -->
