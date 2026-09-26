---
id: TASK-6
title: Conversation view — group emails into threads in the list UI
status: To Do
assignee: []
created_date: '2026-07-24 04:59'
updated_date: '2026-09-26 02:24'
labels:
  - ui
  - ux
dependencies: []
priority: low
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Many mail clients collapse a back-and-forth into one row in the list view; ownmail currently shows every message as a separate flat row, which gets cluttered fast on active threads. Umbrella task; see subtasks for data-model and UI work. Lists now mix Active mail with archived mail (TASK-28, TASK-108), so a thread can span both. Bulk selection moves messages to ownmail's local bin (doc-9), and that action needs a defined thread-level behavior, to be resolved in the UI subtask. Server cleanup no longer depends on this work: TASK-38 protects live threads using provider thread state, without stored grouping.
<!-- SECTION:DESCRIPTION:END -->
