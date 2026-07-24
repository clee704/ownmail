---
id: TASK-2.2
title: Rewrite CONTRIBUTING.md as repo rules/conventions for humans and AI
status: To Do
assignee: []
created_date: '2026-07-24 04:42'
updated_date: '2026-07-24 05:10'
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
- [ ] #1 Branch naming convention documented
- [ ] #2 Squash-merge / 1-PR-1-commit policy stated explicitly, tied to why it matters for changelog generation
<!-- AC:END -->
