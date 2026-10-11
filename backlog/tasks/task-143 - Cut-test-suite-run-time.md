---
id: TASK-143
title: Cut test suite run time
status: Done
assignee: []
created_date: '2026-10-11 22:23'
updated_date: '2026-10-11 23:54'
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
- [x] #3 The pre-push hook and CI run the suite in parallel with pytest-xdist, the coverage gate still applies, and repeated full runs show no new flaky failures
- [x] #4 CONTRIBUTING.md and .pre-commit-config.yaml state the measured run time
- [x] #5 The full pre-push gate passes with browser tests required
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

AC #3 (parallel run), partial, blocked on two parallel-only failures:
- pytest-xdist added to the dev extra (deptry DEP002 ignore like the other dev tools). test_restart_failure_is_survivable passed an OSError instance as a subTest kwarg, which xdist cannot serialize; it now labels the subtest with repr(failure).
- Full runs, -n auto (10 workers), coverage on: --dist load 86s, loadfile 70s, loadscope 72s (61s without coverage); serial was about 290s. Coverage 96.69% in each run, same as serial, and the fail_under 95 line is printed ("Required test coverage of 95.0% reached"), so the gate still applies. Passing runs report 5024 passed, matching serial.
- Flaky only in parallel: 4 of 7 parallel runs failed. (1) test_pdf_export.py::test_actual_pdfs_are_readable_and_block_untrusted_resources and ::test_actual_renderer_does_not_execute_unsanitized_page_scripts fail with "PDF rendering timed out". Instrumenting the deadline showed the 5000 ms browser.close() deadline in pdf_renderer.js expires under load (serial: 3.6s and 1.6s per test). Fixing it means changing a product deadline or how the renderer treats a slow close after the PDFs are written, so it needs a decision. (2) test_download_shutdown.py::test_sigterm_reaps_real_detached_download once hung past its 15s communicate timeout (0.38s serial). Suspected: SIGTERM arriving while the server is still inside start_download/start_scheduler; cause not confirmed.
- Hook and CI still run serially; -n auto is not wired in, and the docs still quote ~11s, until the failures above are resolved.

2026-10-11: parallel runs are blocked on TASK-145 (PDF close deadline under load) and TASK-146 (SIGTERM hang during a detached download). AC #3 and #4 wait for both.

AC #3 and #4 (2026-10-11, after TASK-145 and TASK-146):
- Hook and CI pytest now run with -n auto --dist loadfile; addopts unchanged, so a plain pytest stays serial. CI installs the dev extra, which carries pytest-xdist.
- First 5 parallel runs: 3 failed test_actual_renderer_does_not_execute_unsanitized_page_scripts[True] (the TASK-145 slow-close test) with a missing wrapper.pid. The wrapper wrote its PID only after Chromium exited; under load Chromium itself overran the 5s close deadline and the wrapper was killed first. The wrapper now records its PID before launching Chromium (same process, exec keeps the PID); assertions unchanged. Break check: restoring the failing close deadline still fails the test. Observation: removing the renderer's final process.exit() does not fail it (passes in about 33s instead of 9s).
- After the fix, 5 full parallel runs with coverage and browser tests required (10 workers): all 5025 passed, 0 skipped (5025 collected), 61-68s each, coverage 96.69% and 'Required test coverage of 95.0% reached' printed each time.
- pre-commit run -a --hook-stage pre-push: passed in 69s. CONTRIBUTING.md and .pre-commit-config.yaml now say ~70s and that the gate runs in parallel.

2026-10-11: final pre-push gate passed in parallel with browser tests required, 69s wall time (was about 315s).
<!-- SECTION:NOTES:END -->
