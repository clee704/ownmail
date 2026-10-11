---
id: TASK-143
title: Cut test suite run time
status: In Progress
assignee: []
created_date: '2026-10-11 22:23'
updated_date: '2026-10-11 22:46'
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
- [x] #2 Browser tests reuse one browser per test process, each test still gets a fresh browser context, and the tests still fail when the behavior they cover is broken
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

AC #2 (shared browser):
- tests/conftest.py starts one Playwright browser server per pytest process (session fixture browser_server: launchServer on 127.0.0.1 port 0, endpoint exported as OWNMAIL_BROWSER_WS_ENDPOINT, so xdist workers each get their own). Test scripts call connect() instead of launch(); every test still makes its own newContext/newPage and browser.close() discards it. The function fixture browser_node replaces the contrast_browser probe and its download_browser/label_browser aliases, and fails with the server log if the browser died. Server exits when the browser closes or when pytest closes its stdin. OWNMAIL_BROWSER_ENGINE, OWNMAIL_BROWSER_EXECUTABLE, PLAYWRIGHT_NODE_MODULE and the OWNMAIL_REQUIRE_BROWSER_TESTS skip/fail behavior are unchanged.
- 15 browser test files, 334 tests, serial, no coverage: 154.2s to 137.7s wall, 124s to 99s CPU. Launch is cheaper than estimated here (launch script 0.31s vs connect 0.25s); Node startup plus require('playwright') (about 0.17s) is now the main fixed cost per test. A persistent Node runner would remove it but runs every test script in one process.
- Break checks, each failing then restored: list density fallback (4 failed), CSRF header (2), download counts text (5), contrast ratio (9), duplicate label check (1). Repeated three files in one process with --keep-duplicates: 56 passed. Killing the server or its browser fails the next test at setup with the log. WebKit: 4 test_label_editor failures existed before this change and are unchanged.
<!-- SECTION:NOTES:END -->
