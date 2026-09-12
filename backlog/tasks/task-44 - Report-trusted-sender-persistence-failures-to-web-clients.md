---
id: TASK-44
title: Report trusted-sender persistence failures to web clients
status: To Do
assignee: []
created_date: '2026-09-12 21:27'
labels:
  - web
dependencies: []
priority: medium
type: bug
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The trust-sender and untrust-sender routes in ownmail/web.py catch configuration read/write failures and still return a successful HTTP response. The reader therefore cannot distinguish a saved preference from a persistence failure. Confirmed by source inspection during TASK-32; this behavior predates the UI revamp. Keep this backend correction separate from the presentation and interaction changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A configuration read or write failure returns an actionable error response without claiming that the preference was saved.
- [ ] #2 In-memory trusted-sender state remains consistent with the documented persistence outcome.
- [ ] #3 Regression tests cover successful changes, failed persistence and retry for both routes.
<!-- AC:END -->
