---
id: TASK-6.2
title: Collapse email list into per-thread rows with expand-to-view
status: To Do
assignee: []
created_date: '2026-07-24 04:59'
updated_date: '2026-07-24 05:10'
labels: []
milestone: m-3
dependencies:
  - TASK-6.1
parent_task_id: TASK-6
priority: medium
ordinal: 13
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Once thread grouping exists (TASK-6.1), collapse the search/list views to one row per thread (subject, participant summary, most-recent snippet/date, unread/message count badge), expanding to individual messages on click - similar to Gmail/most modern clients. Needs explicit decisions on: how a thread interacts with label: search (show thread if any message matches, Gmail-style?), how the existing bulk-select/trash UI from 9494f50 applies at thread granularity (trash whole thread vs. single message - probably needs both, similar to how Gmail's UI works), and how unread-count badges interact with TASK-5.3 (read/unread standardization) once that lands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 List/search views show one row per thread by default, not one row per message
- [ ] #2 A thread row expands to show its individual messages
- [ ] #3 Bulk actions (trash, etc.) have defined, tested behavior at both thread and individual-message granularity
<!-- AC:END -->
