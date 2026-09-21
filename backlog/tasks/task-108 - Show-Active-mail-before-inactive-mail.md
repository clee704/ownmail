---
id: TASK-108
title: Show Active mail before inactive mail
status: Done
assignee: []
created_date: '2026-09-21 08:35'
updated_date: '2026-09-21 08:43'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 109000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Order consolidated message results with Active mail first, preserving the selected order within Active and inactive groups.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Active-only and linked Active messages precede inactive messages for date and relevance sorts.
- [x] #2 Pagination preserves the complete grouped order without omissions or duplicates, including archive-only search matches.
- [x] #3 Required repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Active results are grouped before pagination while preserving date or relevance order within each group. Limited searches fetch linked Active matches separately so archive-only matches remain eligible for the first page. Both indexes use the same email-ID tie order as the merge to prevent duplicates or omissions at page boundaries. Regression cases failed before implementation; 170 focused search, database, and web tests pass.

Ownership behavior is unchanged: verified owned mail is excluded from Active tracking and its cached copy retires immediately after capture. Linked-result coverage preserves read-time compatibility for legacy duplicates only.

Full suite: 3,802 passed, one expected failure, 96.36% branch-inclusive coverage. Re-running the complete pre-push gate after automatic formatting.

Final pre-push gate passed, including formatting, lint, dependency checks, and the full suite.
<!-- SECTION:NOTES:END -->
