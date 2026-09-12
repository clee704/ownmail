---
id: TASK-32.3
title: Improve message list hierarchy and search layout
status: To Do
assignee: []
created_date: '2026-09-12 18:33'
labels:
  - ui
  - ux
dependencies:
  - TASK-32.1
parent_task_id: TASK-32
priority: medium
ordinal: 3
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make sender, subject, preview and date easy to scan. The current page stops growing at 1100px, reserves 200px for every sender and puts subject and preview in one clipped row. Synthetic browser inspection reproduces truncated sender/label names and competing subject/preview text.

Apply TASK-32.1's visual direction to search controls, list rows, selection toolbar and pagination. Use available width deliberately, give subject and preview distinct visual roles, and preserve useful message information on narrow screens. Thread grouping remains TASK-6; query correctness remains TASK-21 and TASK-22. Keep doc-9's decision to omit per-row label chips and TASK-5.3's decision not to archive read/unread state.

Evidence: ownmail/static/style.css (.ownmail-email-sender, .ownmail-email-row-content, subject/snippet/date rules); ownmail/templates/search.html and _email_list.html.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Sender, subject, preview and date have a consistent visual hierarchy in light/dark views, demonstrated with short/long subjects, missing subjects, long senders and CJK text.
- [ ] #2 List columns respond to available width; narrow layouts retain sender, subject and date without page-level horizontal scrolling or overlapping selection controls.
- [ ] #3 Search, sorting, selection count and pagination have clear grouping and labels; opening a message remains distinct from selecting it.
- [ ] #4 Existing query, sort and pagination behavior is preserved, with no unread badges or per-row label chips added; record visual checks at 390px, 768px and 1440px.
<!-- AC:END -->
