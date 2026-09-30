---
id: TASK-123
title: Remove duplicate HTML sanitizer unit tests
status: To Do
assignee: []
created_date: '2026-09-30 02:12'
labels:
  - web
dependencies: []
references:
  - tests/test_sanitizer.py
priority: low
type: chore
ordinal: 26800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
tests/test_sanitizer.py tests the same sanitize, kill and stop paths twice. TestHtmlSanitizerUnit duplicates TestSanitizeErrorHandling (test_sanitize_without_node_returns_escaped / test_unavailable_sanitizer_escapes_input, test_sanitize_with_mocked_process / test_successful_response_is_returned, test_sanitize_process_died / test_dead_worker_triggers_restart, test_sanitize_broken_pipe / test_broken_pipe_triggers_restart, test_sanitize_dompurify_error / test_worker_error_field_escapes_input) and TestSanitizerLifecycle (test_kill_process_handles_timeout / test_kill_escalates_to_sigkill_on_timeout, test_stop_without_start / test_stop_without_worker_is_a_noop). TASK-118 removed the duplicated start() and dependency tests; these remain.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each sanitize, kill and stop path is covered by one test, keeping the stronger assertion of each pair
- [ ] #2 Coverage does not drop and the full pre-push gate passes
<!-- AC:END -->
