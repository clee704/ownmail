---
id: TASK-147
title: Make Ctrl-C and interrupt tests pass under heavy load
status: Done
assignee:
  - codex
created_date: '2026-10-17 05:31'
updated_date: '2026-10-21 04:44'
labels:
  - testing
dependencies: []
references:
  - tests/test_pdf_export.py
  - tests/test_pdf_export_cli.py
  - tests/test_download_progress.py
priority: low
type: bug
ordinal: 118000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Several signal-timing tests fail when the machine is heavily loaded and pass when rerun alone, so a pre-push gate run can fail for reasons unrelated to the change being pushed.

Evidence from 2026-10-16 (TASK-142 work): a Chromium pre-push gate run and a WebKit full-suite run, both with -n auto while other browser probes ran (load average about 18), failed the same four tests:
- tests/test_pdf_export.py::test_actual_ctrl_c_stops_renderer_child: the caller subprocess timed out after 8 seconds.
- tests/test_pdf_export.py::test_stubborn_renderer_descendant_is_stopped_with_bounded_cleanup[ctrl-c-inherited-output] and [ctrl-c-closed-output]: the caller subprocess timed out after 6 seconds.
- tests/test_download_progress.py::test_interrupt_flushes_current_counts_without_message_errors[downloading]: ImapProvider was expected to be called once and was called twice.
All eight cases passed when rerun alone, and the next gate run on a quiet machine passed. Earlier, tests/test_pdf_export_cli.py::test_actual_ctrl_c_stops_renderer_child failed once in a full gate run and passed alone.

The PDF tests wait on fixed wall-clock timeouts. The second ImapProvider call suggests the interrupt landed after the next source had started, so that test may race the download loop rather than only wait too briefly (unverified). Related load flakes: TASK-145 (PDF close deadline) and TASK-146 (SIGTERM hang during a detached download).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Test-harness timing and signal-state assumptions are documented with controlled reproductions; uncertainty about the exact historical failures is recorded explicitly
- [x] #2 The listed tests pass in repeated full parallel runs while a second browser suite runs concurrently, and still fail when the Ctrl-C or interrupt handling they cover is broken
- [x] #3 Any product deadline change is decided by the maintainer before it lands
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: aee1c8efc36ea92c24288fc7c71bc43081f644ea.
1. Trace and reproduce each listed signal-test failure; distinguish harness races from product defects.
2. Make bounded test-harness fixes, preserving signal and cleanup assertions. Product deadline changes require a separate maintainer decision.
3. Verify regression tests with deliberate handler breakage, then run repeated full parallel suites with a concurrent browser suite.
4. Review the full task diff, run the required pre-push gate, record evidence, and commit on master.
Scope excludes product deadline changes, unrelated signal behavior, and WebKit label-editor repairs (TASK-144).
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Started from a clean master checkout. No other task is In Progress. Selected as the first unfinished eligible task in doc-4.

Verified harness behavior:
- PDF tests previously waited only for a PID file written by the renderer or descendant. That does not prove the Python caller has returned from Popen or entered its protected wait. A controlled SIGSTOP after launch and before that wait reproduces the original 8-second communicate TimeoutExpired. The revised caller acknowledges its protected wait after the synthetic child is ready; all three Ctrl-C cases pass with the caller held for 9 seconds before that acknowledgement.
- Timeout cases previously charged interpreter/descendant startup to their 6-second watchdog and could expire the 1-second renderer timeout before the synthetic descendant existed. All three now pass with an injected 2-second renderer startup delay. Readiness allows 30 seconds; the post-readiness 8-second/6-second watchdogs and renderer termination grace periods are unchanged.
- The download test called the inherited SIGINT handler synchronously. Active sync installs no handler, so the test depended on ambient process state. It now raises KeyboardInterrupt at the provider read boundary, as the checking case already does, and asserts that the intended reads occurred with final-snapshot diagnostics on failure. A no-op inherited handler no longer affects either case.
- Mutation checks: removing renderer-group signals fails all six PDF cases on surviving-process assertions; clearing the live-sync interrupted result fails both progress cases because the later source runs. Product files and deadlines are unchanged.
Evidence limits: the controlled PDF scheduling probe demonstrates the original timeout mechanism, but there is no trace proving it caused the historical run. The historical download failure is still unexplained: 536 relevant tests passed twice with no SIGINT handler leak at test boundaries, and an earlier sync_live exception could also explain a second provider construction. On 2026-10-20 the maintainer explicitly accepted the documented uncertainty and authorized revising AC #1 and closing this task.
Baseline validation: 5,123 tests passed under full -n auto coverage with a concurrent 129-case Chromium browser suite at -n 4; coverage 96.70%. Three browser runs passed. The patched runs are recorded below.

Confirmed independent discovery filed as TASK-150: Ctrl-C during renderer launch can leave the detached renderer alive. The parent independently reproduced caller exit 42 with the renderer still running, then killed the synthetic group. This product fix remains outside the current harness change.

Patched validation complete: two successive full -n auto coverage runs passed all 5,123 tests (122.35s and 121.75s), each while a separate 129-case Chromium browser suite ran at -n 4. Both coverage runs reached 96.70%. The 94 tests in the three referenced files also passed at -n auto. The parent independently reran the progress mutation (both cases fail when interrupted is cleared) and inherited-no-op-handler probe (both cases pass). All five concurrent browser runs passed. The required pre-push gate passed; an earlier run passed every test but pre-commit rejected it because task metadata changed while the hook was running. The successful rerun left repository files untouched.
Review: checked the full task diff against aee1c8efc36ea92c24288fc7c71bc43081f644ea. No product code changes or unresolved patch findings; the launch-cancellation discovery is tracked in TASK-150. The historical download failure remains unverified under the revised completion criterion.

Completion: test fixes committed as 893189a on master; validation and TASK-150 recorded in a2de0a5. All revised acceptance criteria are met. No product files or deadlines changed.
Resume action: instrument the original progress test at the review base to capture its inherited SIGINT handler, provider read calls, source result and progress snapshot before the provider-count assertion, then repeat the full parallel/browser-load scenario until the unexplained failure is captured. The captured failure is needed to distinguish a pre-read error from handler state.
Validation commands: `.venv/bin/python -m pytest tests/test_pdf_export.py tests/test_pdf_export_cli.py tests/test_download_progress.py -q -n auto --dist loadfile`; two sequential `OWNMAIL_REQUIRE_BROWSER_TESTS=1 .venv/bin/python -m pytest --cov=ownmail -q -n auto --dist loadfile` runs while an independent loop ran `OWNMAIL_REQUIRE_BROWSER_TESTS=1 .venv/bin/python -m pytest -q -n 4 --dist loadfile tests/test_email_contrast.py tests/test_reader_fonts.py tests/test_reader_body_style.py tests/test_reader_scroll.py tests/test_reader_navigation.py tests/test_csrf_browser.py`; `PATH="$PWD/.venv/bin:$PATH" OWNMAIL_REQUIRE_BROWSER_TESTS=1 pre-commit run -a --hook-stage pre-push`.

All temporary scheduling/mutation probes and stress-run logs were removed after recording their results. Synthetic probe processes were stopped. No unresolved patch findings remain. Product files and deadlines are unchanged.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Stabilized signal tests with explicit renderer readiness and deterministic provider interruption. Repeated full parallel/browser-load runs and mutation checks pass; required pre-push gate passes. The maintainer accepted documented uncertainty about the exact historical failures. The separate launch-cancellation defect remains in TASK-150.
<!-- SECTION:FINAL_SUMMARY:END -->
