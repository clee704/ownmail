---
id: TASK-121
title: Show why the sanitizer worker failed to start
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-30 02:12'
updated_date: '2026-09-30 13:16'
labels:
  - web
dependencies: []
references:
  - ownmail/sanitizer/__init__.py
priority: low
type: bug
ordinal: 26600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
HtmlSanitizer._drain_stderr logs the worker's stderr at debug level, and no logging is configured, so when worker.js exits before its ready line the reason never reaches the user. ownmail serve reports only that the worker did not start, with generic advice to check the Node.js version or delete node_modules. Two likely causes produce this: a Node.js release older than jsdom 26 supports (Node 18), and a node_modules tree missing a package, which fails with MODULE_NOT_FOUND. The second was reproduced by deleting a transitive package, and an npm install killed before TASK-118 added its unfinished-install marker can leave it. Surfacing the worker's first error line lets the user tell these apart.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 When the worker exits before signaling ready, the refusal names the worker's first error line, such as a missing module or a syntax error
- [x] #2 A worker that is still running but sends an invalid ready line is reported without waiting on its stderr
- [ ] #3 Tests cover both paths and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Claim TASK-121 on isolated branch fix/sanitizer-startup-diagnostics from clean review base 9a86e82ecc72440ecfb13671531a82f85f45c1ec. Commit this task-only plan with normal hooks before production or test edits; preserve that review base through final review.
2. Extend only TestSanitizerLifecycle with synthetic process/pipe/thread regressions for missing-module and syntax diagnostics after location/source preambles, unchanged no-error fallback, live invalid readiness without stderr waits, exited-worker drain races, restart isolation and bounded capture. Preserve a failing baseline against current startup behavior before implementation.
3. Bind each drain to its own process and fresh capture state. Scan at most 32 startup physical-line prefixes using reads bounded to 1,024 characters; retain only the first recognized error summary, capped at 512 printable characters. Keep draining after capture stops without retaining or logging arbitrary preamble, stack or runtime message text. Disable capture before publishing successful readiness and on every completed startup attempt. Preserve existing readiness parsing, generic fallback, repair guidance and process cleanup behavior.
4. On unsuccessful readiness, permit a drain-thread join of at most one second only after that worker poll confirms exit. Never synchronously read stderr or join its thread when the worker is still running. Keep diagnostics isolated across restarts and avoid mutable-process lookup races. Do not change worker.js, dependency installation/locking, web refusal status/order or other sanitization behavior.
5. Run focused lifecycle and retained sanitizer/startup tests with private synthetic fixtures, Ruff check/format-check, deptry and whitespace checks. Review the whole diff against the fixed base, including independent Astra Ultra review for the lifecycle/race boundaries. Resolve findings without widening scope and commit a clean reviewed checkpoint with normal hooks.
6. Report readiness while TASK-93 owns Chromium. Once its browser interval is released, run the complete required mandatory-browser pre-push gate with unchanged assertions, timeouts, coverage floor and test selection. Mark Done only after every acceptance criterion and required check passes, then close through the supported ledger workflow and normal hooks. No main changes, integration, merge/rebase, publication or next task.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified read-only on clean completed TASK-115 revision 9a86e82ecc72440ecfb13671531a82f85f45c1ec before claim. TASK-121 is the next recorded item after TASK-115 (doc-4 position 26b), was To Do/unassigned and has no dependencies. Fully mocked actual HtmlSanitizer.start and run_server calls confirmed that missing-module and syntax-error diagnostics reach the stderr drain but are absent from both sanitizer.error and the printed refusal. The live-worker invalid-ready baseline performs no synchronous stderr reads or drain-thread join; that behavior must be retained. No real worker, browser, mail, configuration or credential operations were needed.

Authorized ownership is sanitizer/__init__.py startup/drain lifecycle, TestSanitizerLifecycle hunks in tests/test_sanitizer.py, and this ledger. Production web/error-status behavior belongs to TASK-122; worker/rendering/padding behavior belongs to TASK-93 and remains untouched. Existing repair guidance and unavailable-on-failure behavior remain. Independent Astra Ultra design review confirmed the bounded approach and identified two required protections: each thread must retain its original process/capture rather than reading mutable self._process, and bounded reads must skip continuation fragments rather than allocating unrestricted stderr lines and slicing afterward.

Only one recognized startup error summary will be retained/reported, with bounded scanning/length and printable output. Startup occurs before any mail request; capture stops before successful readiness is published. Arbitrary preambles, full stacks and runtime message text will be drained without being copied into diagnostics or debug output. No credential/environment collection, schema/dependency changes, new query/API behavior, security-policy relaxation or process/ready-timeout redesign is included.

Next action: commit this task-only claim/plan with normal hooks before adding the synthetic failing regressions.

Implementation checkpoint chronology: task-only claim/plan 038d913a26eaf857e16a7bc7d71804089d2b0cd8 was committed with normal hooks before tests or production edits. The first synthetic regression run against unchanged production recorded 11 failures and 11 passes; the initial bounded implementation then passed all 17 lifecycle tests.

Implemented worker-bound stderr drains with fresh local capture state, fixed-size reads, physical-line and printable-summary bounds, first recognized error only, and capture disabled before readiness and after unsuccessful starts. Generic fallback and repair text remain exact. Live nonempty invalid readiness performs no synchronous stderr read or drain join. Mocked actual run_server calls verified missing-module and syntax-error summaries appear in the refusal, retain pipx repair guidance and prevent app creation without editing web code.

Independent Astra Ultra implementation review identified an EOF/exit timing race: stdout can close just before poll reports exit. A targeted regression failed before correction. The EOF path now uses the already-required process cleanup to confirm exit, then performs the same bounded join only after re-polling the original process. Live invalid readiness remains unchanged. Printable filtering is now asserted through a synthetic NUL-bearing error summary. No process-wait timeout or readiness protocol was changed.

Current validation: 122 retained sanitizer and TestRunServer tests passed, including the new EOF race regression; Ruff check, Ruff format-check, deptry and whitespace checks passed. Scope verification proves tests outside TestSanitizerLifecycle are byte-identical and all sanitizer AST outside startup/drain and four diagnostic constants is unchanged. Full required browser/pre-push gate remains pending, so AC 3 is unchecked and the task remains In Progress.

Next action: finish author/independent review, commit the reviewed implementation with normal hooks, then run the granted complete mandatory-browser pre-push gate before closure.

Author full-diff review completed against the fixed review base; no unrelated paths, supported behavior removals or weakened assertions were found. Independent Astra Ultra re-review confirmed the EOF-race correction and printable-output regression, with no remaining findings. TASK-122 is ready for its browser gate, so the unused browser interval was released before launching any TASK-121 browser process. This is a reviewed implementation checkpoint, not task completion.

Next action: run the prepared full mandatory-browser pre-push gate after TASK-122 releases Chromium; then close only if every required check passes.
<!-- SECTION:NOTES:END -->
