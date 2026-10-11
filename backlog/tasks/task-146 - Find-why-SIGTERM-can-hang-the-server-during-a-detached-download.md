---
id: TASK-146
title: Find why SIGTERM can hang the server during a detached download
status: To Do
assignee: []
created_date: '2026-10-11 22:58'
labels:
  - downloads
dependencies: []
priority: medium
type: bug
ordinal: 117000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/test_download_shutdown.py::test_sigterm_reaps_real_detached_download hung past its 15-second timeout once in seven parallel suite runs (TASK-143); it takes about 0.4s serially. Suspected cause, unconfirmed: SIGTERM arrives while the server is still inside start_download or start_scheduler.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The cause of the hang is identified and recorded
- [ ] #2 If the cause is in product code, SIGTERM during download or scheduler startup stops the server and reaps the download within a bound
- [ ] #3 A test reproduces the timing deterministically and fails before the fix
<!-- AC:END -->
