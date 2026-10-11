---
id: TASK-143
title: Cut test suite run time
status: In Progress
assignee: []
created_date: '2026-10-11 22:23'
updated_date: '2026-10-11 22:32'
labels:
  - testing
dependencies: []
priority: medium
type: chore
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The pre-push gate takes about five minutes. A profile showed about 370 tests (7% of the suite) taking 87% of the time: browser tests start Node and launch a new Chromium per test, retry tests sleep through real Retry-After delays, the stuck-renderer PDF test waits out its real grace period, and the suite runs in a single process. Coverage adds about 9%. CONTRIBUTING.md and .pre-commit-config.yaml still quote ~11s. Reduce wall time without weakening any test: every changed test must still fail when the behavior it covers is broken.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Retry and cleanup tests no longer wait in real time; each still asserts the delay or bound it covers and fails when the retry or kill path is broken
- [ ] #2 Browser tests reuse one browser per test process, each test still gets a fresh browser context, and the tests still fail when the behavior they cover is broken
- [ ] #3 The pre-push hook and CI run the suite in parallel with pytest-xdist, the coverage gate still applies, and repeated full runs show no new flaky failures
- [ ] #4 CONTRIBUTING.md and .pre-commit-config.yaml state the measured run time
- [ ] #5 The full pre-push gate passes with browser tests required
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC #1 (retry and cleanup waits):
- Gmail live 429 tests in test_live_gmail_scope.py and test_live_providers.py now use a sleep spy (reusing test_live_gmail_batch.batch_retry_sleep in the scope module) and assert the 1.0s then 2.0s backoff. About 9s saved.
- test_stubborn_renderer_descendant_is_stopped_with_bounded_cleanup: pdf_export now names its SIGTERM grace periods (_TERM_GRACE_SECONDS = (5, 1)) because the caller runs in a subprocess and could not reach the literals; the test sets (0.3, 0.1) and keeps the real SIGTERM-ignoring processes. stubborn-leader 7.3s to 1.7s. The 1s renderer timeout in the timeout cases stays so the descendant always spawns first.
- Inter-batch pacing: test_imap_provider.py zeroes FOLDER_BATCH_DELAY with an autouse fixture (1.5s saved); two Gmail batch tests patch time.sleep and one asserts the BATCH_DELAY request (0.4s saved).
- Break checks run, each failing the changed tests then restored: skip the live Gmail retry, flatten the backoff to 1.0s, drop the final SIGKILL, block on the first SIGTERM wait, drop the Gmail batch delay.
- Left alone: test_download_progress_integration.py sleeps are subprocess synchronization; removing the listing sleep made the test fail. test_live_gmail_batch 1000-message tests are CPU-bound (sleep already mocked).
<!-- SECTION:NOTES:END -->
