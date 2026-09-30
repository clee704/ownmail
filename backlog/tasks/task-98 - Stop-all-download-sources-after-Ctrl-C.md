---
id: TASK-98
title: Stop all download sources after Ctrl-C
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-21 03:16'
updated_date: '2026-09-30 07:41'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 13000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
When a provider download catches KeyboardInterrupt and returns interrupted=True, cmd_download prints Download Paused but continues authenticating and downloading later configured sources. A single Ctrl-C should stop the overall command after retaining completed work and reporting the partial result.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An interrupted source stops the source loop before constructing or authenticating the next provider.
- [x] #2 Completed saves and counters remain available, the command returns failure, and the overall summary identifies interruption.
- [ ] #3 A multi-source regression covers interruption during live enumeration and verifies later sources are untouched; full pre-push checks pass.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Use isolated branch fix/stop-download-sources-on-interrupt from reviewed reconciliation closure 8a2e1b25de4f4fac4fc4c5792abbb17366d3b909. Verify the task premise with synthetic calls and commit this task-only plan before implementation.
2. Change only cmd_download in ownmail/cli.py: after the interrupted source has closed its provider, accumulated counts and flushed interruption progress, stop the outer source loop and identify interruption in the overall summary. Preserve its failure return and all completed work.
3. Strengthen TestCmdDownloadSources in tests/test_cli.py for both provider orders, first/last interruption, constructor exclusion, exact counts and summary. Extend the existing interruption family in tests/test_download_progress.py to exercise actual archive.backup and live enumeration with synthetic providers; preserve saved data and the interrupted progress identity. No real mail, credentials or source operations.
4. Run failing-before/passing-after focused regressions, retained download/live/locking checks, explicit Ruff check and format-check, deptry and the complete mandatory-browser pre-push coverage gate with private runtime state. Review the complete change against the original task base.
5. Update verified acceptance criteria and commit local closure with normal hooks. Preserve all completed branches and clean state. No master update, merge, rebase, publication, TASK-37 policy or TASK-125 work.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified on the reviewed reconciliation base: an actual cmd_download call with two mocked providers still constructs, authenticates and backs up the second source after the first returns interrupted=True. It returns False but includes the later download in the overall count and publishes a later starting phase. Both ordinary backup and live sync already return the interruption flag; the missing stop is in the shared CLI result path. Independent Astra Ultra read-only preflight confirms this is bounded and disjoint. Review base: 8a2e1b25de4f4fac4fc4c5792abbb17366d3b909. Existing test_interrupted_download_reports_resume incorrectly expects both sources to contribute after first-source interruption; correcting that expectation will be paired with stronger provider-construction assertions. Tests use private synthetic fixtures and mock auto_expire_trash and all provider authentication; no existing archive or credential store is accessed. Minimal production ownership is cmd_download result aggregation and overall summary only; tests/test_cli.py, tests/test_download_progress.py and this task ledger are the remaining owned files. Accountless-row policy, CSP, provider/authentication implementations, schema, storage semantics and other queued tasks are outside this task.
Next action: create a source-bound private test environment and commit this task-only plan with normal hooks before changing product code or tests.

Task-only claim/plan checkpoint b9a2dee6290b376e85fd3e2cc2469f1569ec40a5 was committed with normal hooks before product or test implementation. Six strengthened cases failed against unchanged production code: first-source interruption still constructed the next provider, and the overall summary did not identify interruption. The implementation adds the stop only after current-source cleanup, accumulated counts and progress failure/flush, then adds an explicit overall interruption line while retaining resume guidance and False return. Existing parameterized summary coverage now checks both provider orders and both interruption positions, exact downloaded/error totals, no later constructor/authentication and IMAP close. The old first-interruption expectation of three downloads was demonstrably preserving the bug; it is now one, with stronger exclusion assertions. Existing actual CLI/live-enumeration tests now use two synthetic sources and verify exit 1, unchanged interrupted-source identity, retained counts and byte-identical saved synthetic mail. All provider constructors/authentication and trash expiry are mocked; no real mail or credentials are accessed. The focused download/progress/locking/shutdown/live suite passed 141 tests in 3.98 seconds. Ruff check, explicit format-check for all 118 Python files, deptry and whitespace checks pass. No product paths outside cmd_download changed. Next action: commit this focused checkpoint with normal hooks, run the complete mandatory-browser pre-push gate in private runtime state, and complete author review/verified ledger closure.
<!-- SECTION:NOTES:END -->
