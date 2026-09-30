---
id: TASK-12
title: Global --verbose is dropped when placed before the subcommand
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-07-24 20:55'
updated_date: '2026-09-30 12:15'
labels: []
dependencies: []
priority: low
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
`ownmail --verbose verify` runs with verbose=False; `ownmail verify --verbose` works.

_add_global_opts() in ownmail/cli.py adds a second -v/--verbose (store_true, default False) to every subparser so the flag works 'in any position'. Because both use dest='verbose' and share one namespace, the subparser parse runs second and overwrites the global True with its own False default. The helper defeats the thing it exists to enable.

Fix candidates: give the subparser copies default=argparse.SUPPRESS, or a distinct dest that is OR-ed with the global value.

Found while writing CLI tests for TASK-3; a test asserting the pre-subcommand form is left out until this is fixed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Actual main preserves -v/--verbose before and after existing supported commands, including repeated flags, while omitted verbose remains False and unsupported nested flag positions remain unsupported.
- [x] #2 Synthetic regressions verify dispatched verbose values and existing error/traceback behavior, fail against the old duplicate default, and pass after the bounded fix without real configuration, archive, provider or credential operations.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-12 on isolated branch fix/preserve-global-verbose from clean review base 90cf67cd2a243297b77b9846fa8f29fe115a2efe. Record explicit acceptance criteria and commit this task-only plan with normal hooks before test or production edits; keep this review base for whole-task review.
2. Strengthen the existing main verify dispatch and unexpected-error traceback regressions using mocked configuration, archive construction and commands. Cover omitted flags, both spellings before and after the top-level command, repeated flags and the already-supported nested placements. Preserve the original-code failing baseline; do not access real archives, configuration, credentials, providers or browser state.
3. Add default=argparse.SUPPRESS only to the duplicate subparser verbose argument. Keep the root default False, existing parsing and error behavior, and unsupported nested-command flag positions unchanged. Do not restructure dispatch or change command, provider, sanitizer, schema, dependency or credential behavior.
4. Run focused and retained CLI checks, Ruff check and format-check, deptry, whitespace checks and author self-review against the fixed review base. Use fresh Astra Ultra support if useful. Preserve a clean reviewed implementation checkpoint and report full-gate readiness while TASK-56 owns Chromium.
5. After the coordinated browser interval is granted, run the complete required mandatory-browser pre-push gate with private runtime state and unchanged tests, coverage floor, assertions and timeouts. Close through the supported task workflow and normal hooks only after all required checks pass. No main changes, integration, rebase/merge, publication or next task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified read-only on clean completed TASK-64 revision 90cf67cd2a243297b77b9846fa8f29fe115a2efe before claim. Doc-4 places TASK-12 directly after TASK-64, and TASK-12 was To Do/unassigned with no dependencies. The root -v/--verbose argument uses store_true and the top-level subparsers duplicate it with an implicit False default. Fourteen synthetic calls to actual main confirmed that either spelling before verify, including repeated pre-command flags, is overwritten to False; post-command and both-position flags reach True. Injected command failures exit 1 on the overwritten paths instead of reraising the original exception as existing verbose behavior requires. Configuration loading, validation, archive-root lookup, archive construction and the verify command were mocked; no keychain call, real archive/configuration access or browser action occurred. Independent Astra Ultra source review confirmed the cause and bounded fix with no dependency, owner-policy or STOP-list blocker.

Owned scope is only the duplicate verbose argument in main._add_global_opts, the existing dispatch/traceback regression families in tests/test_cli.py, and this task ledger. The root default stays False. Existing sources --verbose list is supported and --verbose sources list currently suffers the same overwritten default; sources list --verbose is currently rejected and is outside this task. TASK-56/93 sanitizer work and all held policy/integration work remain untouched. This task originally had no acceptance-criteria section, so explicit criteria are recorded here before implementation.

Task-only acceptance/claim/plan checkpoint c2968e946a2c35f7abd7935718907a55a2c40746 was committed with normal hooks before any test or production edits. The two existing regression functions now exercise actual main with mocked configuration, archive construction and commands. Dispatch cases assert omitted False, both spellings before and after verify, repeated pre/post flags and both positions. Error cases check original exception identity and reporting, nonverbose exit 1, existing nested sources placements, and continued parse exit 2 before configuration loading for unsupported trailing nested flags. Keychain construction is asserted absent.

Against unchanged production code, the strengthened regressions produced 6 failures and 11 passes. Adding default=argparse.SUPPRESS only to the duplicate subparser verbose argument then produced 17 focused passes. All 119 retained CLI tests passed. Ruff check, format-check, deptry and whitespace checks passed without formatting changes. Author review verified the one-line production scope and exact source equivalence outside the two owned test functions. Fresh independent Astra Ultra review found no correctness, scope or test-quality findings. Root defaults, parser definitions, dispatch, existing exception handling and unsupported nested positions remain unchanged.

Both acceptance criteria are verified by focused behavior. The task remains In Progress because the complete required mandatory-browser pre-push gate is still unrun while TASK-56 owns Chromium. Private development dependencies, temporary state and the full-gate command are prepared; no browser was launched. All regression fixtures are synthetic, with no real configuration/archive/credential operations. No integration, publication or next task was performed.

Next action: run the prepared complete mandatory-browser pre-push gate once TASK-56 releases the browser interval; close only after that gate actually passes.
<!-- SECTION:NOTES:END -->
