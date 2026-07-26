---
id: TASK-21
title: 'Multiple label: filters in one query silently return wrong results'
status: To Do
assignee: []
created_date: '2026-07-26 03:20'
labels:
  - bug
dependencies: []
priority: high
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Two independent ways to combine label filters both produce a confidently wrong result set instead of an error.

1. 'label:A OR label:B' silently ANDs. query.py emits OR into the FTS5 MATCH string, but label filters become SQL WHERE clauses that database.search joins with AND. The user asks for a union and gets an intersection.

2. 'label:A label:B' silently drops A. database.search keeps a single 'label_filter' local, so the second __LABEL__ marker overwrites the first (same for __RECIPIENT_EMAIL__ / to:). Only the last filter is applied.

Found while building TASK-5.1 (doc-9), which needed a set union over labels and added 'role:' rather than depending on either of these. Not a blocker for that task.

Either make the combination work (collect a list of label filters; AND them via repeated EXISTS, and support OR groups) or reject it with a parse error. Silently answering a different question than the one asked is the part that has to stop. Same defect shape applies to 'to:' with two email addresses.
<!-- SECTION:DESCRIPTION:END -->
