---
id: TASK-146
title: Find why SIGTERM can hang the server during a detached download
status: Done
assignee: []
created_date: '2026-10-11 22:58'
updated_date: '2026-10-11 23:31'
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
- [x] #1 The cause of the hang is identified and recorded
- [x] #2 If the cause is in product code, SIGTERM during download or scheduler startup stops the server and reaps the download within a bound
- [x] #3 A test reproduces the timing deterministically and fails before the fix
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Cause: test harness only. The test's synthetic server called start_download on the main thread, where web.run_server's SIGTERM handler raises SystemExit. The test signals once the download child prints, which can happen before the parent's Popen returns (it is still reading the exec error pipe) or before _launch stores the Popen object. Under CPU load SIGTERM landed in that window: SystemExit escaped Popen, DownloadManager never recorded the process, stop() had nothing to reap, and the orphaned child kept the server's stdout pipe open, so communicate() timed out even though the server had exited.

Evidence: holding the test's Popen wrapper open after the child starts reproduces the identical TimeoutExpired every time; the original test hung 10 of 300 runs at -n 12 with one yes(1) hog per core.

Product code is not affected: Flask's threaded server calls start_download on request threads and scheduled launches run on the ownmail-downloads thread, so the SIGTERM handler never runs inside Popen. If SIGTERM arrives while a request thread is in start_download, stop() waits on the manager lock until the process is recorded, then reaps it. start_scheduler only starts the watcher thread, and stop() joins that thread with a timeout.

Fix: the test starts the download on a worker thread as production does, holds start_download inside Popen until shutdown begins so every run covers the race deterministically, and asserts start_download returned True. With the old main-thread call the held-window test times out; with the fix it passes. Verified 300 of 300 passes at -n 12 under the same load.
<!-- SECTION:NOTES:END -->
