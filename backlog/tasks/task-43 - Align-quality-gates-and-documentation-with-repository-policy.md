---
id: TASK-43
title: Align quality gates and documentation with repository policy
status: Done
assignee: []
created_date: '2026-09-11 10:54'
updated_date: '2026-09-11 10:56'
labels: []
dependencies: []
priority: medium
type: chore
ordinal: 46000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Audit the developer baseline and repair confirmed mismatches: the full pre-push test hook skips non-Python changes, and contributor documentation has stale coverage and hook-stage descriptions. Keep broader governance changes in TASK-42.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The pre-push test hook runs for configuration and JavaScript-only changes.
- [x] #2 Coverage and hook documentation match the enforced 95 percent gate and configured hook stages.
- [x] #3 The audit records verified strengths and remaining gaps; full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added always_run to the existing pre-push pytest hook so configuration and JavaScript changes cannot skip the full suite. Corrected contributor docs to 95 percent branch-inclusive coverage and tests at push time. Clarified that pre-1.0 releases can have existing archives requiring migrations. doc-10 records the verified baseline and remaining gaps; TASK-42 consolidates the broader governance follow-up.

Validated the repaired hook with only pyproject.toml, CI YAML, and sanitizer JavaScript paths: the full suite ran, with 2189 passed, 1 expected failure, and 95.39 percent overall coverage including branches. All repository-wide commit-stage checks passed; the full pre-push checks also passed for the reload feature. No remote settings or historical acceptance criteria were changed.
<!-- SECTION:NOTES:END -->
