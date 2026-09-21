---
id: TASK-106
title: Retire Active copies immediately after verified capture
status: In Progress
assignee: []
created_date: '2026-09-21 07:53'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 107000
---

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A successful capture removes its Active copy before the next provider read, including partial and interrupted refreshes.
- [ ] #2 Freshly verified owned-content matches retire stale Active entries immediately; failed captures keep their retryable copies.
- [ ] #3 Regression tests, required checks and live verification pass; changes are committed with a clean working tree.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 6dd70a4. Work in the isolated checkout, reuse verified capture and cache boundaries, preserve conservative server-deletion handling, and verify the reported message after applying.
<!-- SECTION:PLAN:END -->
