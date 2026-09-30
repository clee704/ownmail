---
id: TASK-123
title: Remove duplicate HTML sanitizer unit tests
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-30 02:12'
updated_date: '2026-09-30 13:43'
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
- [x] #1 Each sanitize, kill and stop path is covered by one test, keeping the stronger assertion of each pair
- [ ] #2 Coverage does not drop and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-123 on isolated branch test/deduplicate-sanitizer-tests from clean completed TASK-121 review base 31c679bc2095b4516dc8a5ee3794ddae99b9dc67. Commit this task-only plan with normal hooks before test edits; preserve that review base through final review. Production changes are excluded.
2. Record an exact before/after map of eight duplicate tests and every retained assertion. Consolidate the seven named pairs plus the normal-kill overlap into existing error-handling/lifecycle tests. Transfer full escaped-output equality and the combined script/paragraph fixture; strict Boolean identities for unavailable and successful responses; restart/padding checks; timeout process clearing; and normal shutdown stdin-close-once/process clearing before deleting duplicates.
3. Keep distinct broken-pipe-on-close, restart install=False, Node-availability/default-property tests, and every TASK-121 diagnostic/readiness/race test unchanged. Only tests/test_sanitizer.py and this task ledger may change. No production, dependency, schema, configuration, worker, web or API changes.
4. Use private synthetic mocks to validate the retained assertions, including deliberately broken behavior that each transferred guarantee must reject. Run retained sanitizer/startup tests and static checks. Preserve the completed base full-suite coverage data and compare normalized per-file executed statements/arcs and exact totals against final data, not rounded percentages. Capture focused before/after coverage as an additional early check.
5. Perform author full-diff review and an independent Astra Ultra review against the fixed base. Resolve findings without weakening checks, update verified acceptance criteria, and checkpoint the reviewed test-only change with normal hooks.
6. TASK-8 owns Chromium. Report full-gate readiness after focused/static checks; once the browser interval is released, run the full required pre-push gate with mandatory Chromium, private runtime/temp/profile state, original test selection/assertions/timeouts and coverage floor. Mark Done only after coverage preservation and every required check pass. Preserve branches; no main/integration/merge/rebase/push or next task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Read-only preflight verified the current task is To Do/unassigned, with no dependencies, at doc-4 position 26d. The completed TASK-121 lifecycle base is clean; TASK-122 is independently completed, and TASK-8 is the other IC assignment. Source inspection and independent Astra Ultra assertion audit confirmed eight redundant test methods with no product-policy decision. Seven pairs are explicitly named in the description; the eighth normal-kill pair is authorized under the one-test-per-path criterion.

The retained timeout test currently lacks the duplicate's process-cleared assertion. Four retained sanitize failure tests currently check only substrings where duplicates check complete output. Unavailable/success tests also need strict Boolean identity assertions: truthiness and tuple equality would accept integer flags. The retained normal-stop test needs the duplicate's stdin-close-once and process-cleared assertions. All of these must transfer before deletion. Unique close-failure and no-install restart coverage stays.

The existing base full gate passed 4,010 tests with 96.58% branch-inclusive coverage, and its actual coverage database is preserved privately for exact comparison. This task does not relax that coverage-preservation acceptance to merely passing the 95% repository floor. No actual mail/configuration/credentials, browser or external services were used for the premise.

Next action: commit this task-only claim/plan with normal hooks before modifying tests.

Task-only plan commit 1b7162c67a600b6709537c693e4c7acfe54d41ed preceded every test edit and passed normal hooks. The private development environment initially hit sandbox DNS failure; the normal narrowly scoped declared-dependency install succeeded after escalation. No dependency declarations or production files changed.

Before/after assertion mapping (all removed methods were in TestHtmlSanitizerUnit):
- test_sanitize_without_node_returns_escaped -> TestSanitizeErrorHandling.test_unavailable_sanitizer_escapes_input: retain the combined script/paragraph fixture, replace substring checks with complete escaped-output equality, and preserve strict True/False flag identities.
- test_sanitize_with_mocked_process -> TestSanitizeErrorHandling.test_successful_response_is_returned: retain exact returned HTML and preserve strict False/True flag identities instead of equality that also accepts integer values.
- test_sanitize_process_died -> TestSanitizeErrorHandling.test_dead_worker_triggers_restart: transfer complete escaped-output equality and keep the existing restart assertion.
- test_sanitize_broken_pipe -> TestSanitizeErrorHandling.test_broken_pipe_triggers_restart: transfer complete escaped-output equality and keep the existing restart assertion.
- test_sanitize_dompurify_error -> TestSanitizeErrorHandling.test_worker_error_field_escapes_input: transfer complete escaped-output equality and keep the existing padding assertion.
- test_kill_process_handles_timeout -> TestSanitizerLifecycle.test_kill_escalates_to_sigkill_on_timeout: retain kill-once and transfer process-is-None after shutdown.
- test_stop_without_start -> TestSanitizerLifecycle.test_stop_without_worker_is_a_noop: retained test already checks no exception and unavailable state; no transfer needed.
- test_kill_process -> TestSanitizerLifecycle.test_stop_terminates_worker: transfer stdin-close-once and process-is-None while retaining terminate-once and unavailable state.

Assertion transfer preceded deletion: all 27 lifecycle/error-handling tests passed while the duplicate methods still existed. Eleven isolated runtime-only mutations verified the moved guarantees: truncated escaped output in four paths, integer flags in four positions, stale process handles in normal/timeout shutdown and omitted stdin closure. Each mutation passed the old retained counterpart but failed its strengthened version. Production files were never modified for these probes. The exact mapping artifact retains before/after method source privately.

After deleting exactly eight redundant methods, all 114 retained sanitizer/TestRunServer tests passed (baseline 122). Actual focused coverage is identical: 353 executed lines and 511 arcs, covering 321 of 323 statements and 75 of 76 branches. The full base coverage database is preserved; its exact report totals are 8,543/8,744 statements and 3,164/3,378 branches covered, with unrounded aggregate 96.5764725292856%. The final full-suite comparison is still pending and is required for AC 2.

Author full-diff review and independent Astra Ultra review found no remaining issues. Scope checks prove only the eight removals and seven strengthened counterparts changed; every other test/helper method is byte-identical, including TASK-121 diagnostics/races, unique close-failure, restart install=False and availability tests. Production is unchanged. Ruff check, format-check, deptry and whitespace checks passed.

Next action: commit the reviewed test-only implementation with normal hooks, then run the prepared complete mandatory-browser pre-push gate after TASK-8 releases Chromium and compare exact full coverage measurements against the preserved base. TASK-123 remains In Progress until AC 2 is verified; no integration/publication or next task.
<!-- SECTION:NOTES:END -->
