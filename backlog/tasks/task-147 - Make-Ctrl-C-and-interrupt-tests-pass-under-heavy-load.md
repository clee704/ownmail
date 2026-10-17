---
id: TASK-147
title: Make Ctrl-C and interrupt tests pass under heavy load
status: To Do
assignee: []
created_date: '2026-10-17 05:31'
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
- [ ] #1 The cause of each listed failure under load is identified and recorded in this task
- [ ] #2 The listed tests pass in repeated full parallel runs while a second browser suite runs concurrently, and still fail when the Ctrl-C or interrupt handling they cover is broken
- [ ] #3 Any product deadline change is decided by the maintainer before it lands
<!-- AC:END -->
