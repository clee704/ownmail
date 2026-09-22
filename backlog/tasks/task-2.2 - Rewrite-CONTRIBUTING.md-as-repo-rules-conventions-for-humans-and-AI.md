---
id: TASK-2.2
title: Rewrite CONTRIBUTING.md as repo rules/conventions for humans and AI
status: Done
assignee: []
created_date: '2026-07-24 04:42'
updated_date: '2026-09-22 17:25'
labels: []
milestone: m-2
dependencies: []
parent_task_id: TASK-2
priority: medium
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Tighten CONTRIBUTING.md to be the shared human+AI rulebook: formalize Conventional Commits (already documented) with an explicit branch-naming convention (<type>/<short-desc>), and make the squash-merge policy explicit — 1 PR = 1 squashed commit, PR title = that commit's Conventional Commits header, keep each PR/commit self-contained and focused on one change (don't mix refactor + feature). Keep the existing dev setup, testing/coverage, and DB migration sections.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Branch naming convention documented
- [x] #2 Squash-merge / 1-PR-1-commit policy stated explicitly, tied to why it matters for changelog generation
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
**Ledger repair, 2026-09-22 (TASK-42).** Removed number-only accidental criteria and checked the remaining criteria against the current repository.
<!-- SECTION:NOTES:END -->
