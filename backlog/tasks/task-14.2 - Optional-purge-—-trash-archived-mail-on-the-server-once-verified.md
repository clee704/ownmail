---
id: TASK-14.2
title: Optional purge — trash archived mail on the server once verified
status: To Do
assignee: []
created_date: '2026-07-25 05:39'
labels: []
milestone: m-5
dependencies:
  - TASK-14.1
parent_task_id: TASK-14
priority: high
ordinal: 2
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Knob 1 of doc-6, split out of TASK-14. Keeps ALL of TASK-14's STOP-item weight: it deletes user email and needs an OAuth scope widening from gmail.readonly to gmail.modify. Requires explicit human sign-off and lands via PR, not straight to master.

Depends on TASK-14.1 because purge requires download: anything the filter excludes is automatically never purged, and that coupling is what keeps the inbox safe without a dedicated inbox rule.

Scope, ACs and hazards are unchanged from TASK-14 - see that task and doc-6. In particular: purge means move to provider Trash (never hard delete), confirmation is a per-message content-hash re-check at purge time, sweep semantics rather than download-time-only, dry-run by default, and the hazard that narrowing the filter makes the next purge run delete more.
<!-- SECTION:DESCRIPTION:END -->
