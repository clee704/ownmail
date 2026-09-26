---
id: TASK-6.2
title: Collapse email list into per-thread rows with expand-to-view
status: To Do
assignee: []
created_date: '2026-07-24 04:59'
updated_date: '2026-09-26 02:24'
labels: []
milestone: m-3
dependencies:
  - TASK-6.1
parent_task_id: TASK-6
priority: low
ordinal: 32000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Once thread grouping exists (TASK-6.1), collapse the search/list views to one row per thread (subject, participant summary, most-recent snippet/date, message count), expanding to individual messages on click - similar to Gmail/most modern clients. Needs explicit decisions on: how a thread interacts with label: and role: searches and sidebar navigation (show the thread if any message matches, Gmail-style?), how bulk selection to the local bin applies at thread granularity (whole thread vs. single message, probably both), and how Active rows group with archived rows. There is no unread badge: TASK-5.3 decided ownmail does not archive read state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 List/search views show one row per thread by default, not one row per message
- [ ] #2 A thread row expands to show its individual messages
- [ ] #3 Bulk actions (trash, etc.) have defined, tested behavior at both thread and individual-message granularity
<!-- AC:END -->
