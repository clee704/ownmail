---
id: TASK-150
title: Stop the PDF renderer when Ctrl-C arrives during launch
status: Done
assignee:
  - '@codex'
created_date: '2026-10-21 04:36'
updated_date: '2026-10-21 06:15'
labels:
  - pdf
dependencies: []
references:
  - ownmail/pdf_export.py
  - tests/test_pdf_export.py
priority: low
type: bug
ordinal: 118100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A real SIGINT can arrive after subprocess.Popen starts the detached PDF renderer but before _run_renderer stores the process and enters its protected wait. KeyboardInterrupt then propagates past the cleanup block and the renderer survives.

Found while investigating TASK-147. A deterministic synthetic caller wraps Popen, pauses itself with SIGSTOP immediately after the real Popen returns, and writes a readiness marker. Once the renderer writes its PID, the test sends SIGINT and resumes the caller with SIGCONT. The caller exits with the expected interrupted status while os.kill(renderer_pid, 0) still succeeds. Synthetic processes are killed after the probe.

This is a launch-cancellation gap, distinct from the TASK-147 wait-cleanup harness changes. Keep the fix limited to ownership and cancellation during renderer launch; product deadline changes are unnecessary.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Ctrl-C after renderer launch but before the protected wait stops the owned renderer process group
- [x] #2 Cancellation preserves the existing interrupted result and incomplete-export cleanup behavior
- [x] #3 A deterministic regression exercises the launch window and fails before the fix
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 22d3bc375c7e3ad2abb3038cefa4270dbdd2de77.
1. Reproduce cancellation between renderer launch and protected wait with a deterministic synthetic process test.
2. Protect process ownership during launch and retain existing interruption, process-group cleanup and incomplete-export behavior.
3. Verify the regression fails before the fix, run focused PDF tests and the required pre-push gate, then review the full task diff and commit on master.
Scope excludes renderer deadlines, PDF layout, server shutdown and unrelated signal behavior.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Selected as the next eligible unfinished task in doc-4 from a clean master checkout. No task was In Progress. Existing launch assigns Popen before entering its protected wait; this matches the recorded cancellation gap.

Implemented default-SIGINT deferral on the main thread only while Popen constructs and assigns the renderer. The handler is restored inside the existing cleanup protection, then any deferred interrupt is raised. Custom handlers and worker-thread launches retain their behavior; process-group cleanup and deadlines are unchanged.
Regression extends the existing real-Ctrl-C test with a caller stopped after real Popen returns and before assignment. Before the fix, the caller exited 42 while the renderer PID remained alive, failing the expected ProcessLookupError assertion. Both launch and protected-wait variants pass with the fix. Handler restoration is also checked after successful launch and a missing-executable failure.
Focused validation: 42 tests passed in tests/test_pdf_export.py, including existing process-group timeout/cancellation and incomplete-export cleanup cases. Ruff check, format check and git diff --check pass. Full required gate and CLI interruption validation remain pending.

Required validation passed: PATH="$PWD/.venv/bin:$PATH" OWNMAIL_REQUIRE_BROWSER_TESTS=1 pre-commit run -a --hook-stage pre-push. This includes the full coverage suite, browser tests, CLI interruption result, incomplete-export cleanup and existing renderer process-group cleanup checks.
Reviewed the complete production/test diff against 22d3bc375c7e3ad2abb3038cefa4270dbdd2de77. Launch ownership is protected before the deferred interrupt is re-raised; a launch failure without a process re-raises its original exception; existing handlers are restored. No unresolved review findings. All acceptance criteria are verified; implementation commit and task closure are next.

Completed implementation in 7e40d23 on master after the required pre-push gate passed. All acceptance criteria are verified. The existing interrupted CLI status and incomplete-export cleanup remain covered and passing. Final diff review found no unresolved findings. The deterministic launch regression uses only synthetic processes and cleans them up; no task scratch files or processes remain.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed launch-time Ctrl-C cleanup by deferring the default SIGINT handler until the renderer handle is owned, then reusing existing process-group cleanup. The real-signal regression failed before the fix and passes afterward. Focused PDF tests and the required full pre-push gate pass. Implementation committed as 7e40d23 on master.
<!-- SECTION:FINAL_SUMMARY:END -->
