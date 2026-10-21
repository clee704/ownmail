---
id: TASK-150
title: Stop the PDF renderer when Ctrl-C arrives during launch
status: To Do
assignee: []
created_date: '2026-10-21 04:36'
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
- [ ] #1 Ctrl-C after renderer launch but before the protected wait stops the owned renderer process group
- [ ] #2 Cancellation preserves the existing interrupted result and incomplete-export cleanup behavior
- [ ] #3 A deterministic regression exercises the launch window and fails before the fix
<!-- AC:END -->
