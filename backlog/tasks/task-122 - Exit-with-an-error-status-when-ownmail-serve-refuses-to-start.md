---
id: TASK-122
title: Exit with an error status when ownmail serve refuses to start
status: Done
assignee:
  - '@codex-ic2'
created_date: '2026-09-30 02:12'
updated_date: '2026-09-30 13:23'
labels:
  - web
dependencies: []
references:
  - ownmail/web.py
  - ownmail/cli.py
priority: low
type: bug
ordinal: 26700
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
run_server returns normally when it refuses to start, both when the HTML sanitizer is unavailable and when --debug is combined with a non-localhost --host, so ownmail exits with status 0 and a script or service manager cannot tell a refusal from a clean shutdown. The --debug check also runs after create_app, which auto-expires trash, and after the banner prints Running at: for a server that never starts. TASK-118 moved the sanitizer check ahead of both; the --debug check still follows them.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each refusal exits with a non-zero status
- [x] #2 The --debug and non-localhost refusal happens before create_app and before the banner
- [x] #3 Tests cover both refusals and the full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 247aaa08aaa74c8200b763c32aa10c94613c4c12 (completed TASK-93); isolated branch fix/serve-refusal-exit-status.
1. Extend the existing TestRunServer refusal cases and TestMainServeCommand synthetic CLI dispatch coverage; demonstrate nonzero-exit and pre-startup-order assertions failing on the base.
2. Move the existing public-host debug guard ahead of sanitizer startup and app creation, preserving its host allowlist and diagnostics; raise SystemExit(1) for both existing startup refusals. Leave CLI, sanitizer lifecycle and successful startup/cleanup behavior unchanged.
3. Verify local debug, public reload, CLI propagation and shutdown controls; run Ruff check/format-check, deptry, and the full required pre-push browser/coverage gate using private synthetic runtime state after the shared browser interval is released.
4. Review the complete task diff, commit the implementation and verified ledger closure, and preserve the branch without integration or publication.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise confirmed through eight synthetic subprocess observations of the actual CLI/server functions: both entry points exit 0 for sanitizer unavailability and public-host debug refusal. The latter reaches app creation, mocked trash expiration and the Running at banner before refusing. Local-debug/public-reload controls reach the mocked server normally. No real archive, worker, browser or server operations were used.
Scope: ownmail/web.py run_server refusal guards, existing TestRunServer and TestMainServeCommand regressions, and this task record only. TASK-121 owns sanitizer lifecycle code/tests on a separate branch; it is not a technical dependency. A later coordinated combined validation must include its final checkpoint; this task does not merge it. No host/debug policy, archive deletion, credentials, dependencies or security settings change.

Implementation and focused verification: both existing refusal paths now raise SystemExit(1). The unchanged debug-host guard runs before sanitizer construction, app creation or the startup banner. Allowed localhost debug, public-host reload and successful shutdown behavior are preserved.
Red evidence: the original implementation fails 8 refusal regressions while 21 controls pass. An exit-code-only intermediate change still fails 5 startup-order regressions while 24 controls pass. Final focused startup, CLI error-handling and download-shutdown coverage passes all 41 tests. Eight synthetic subprocess entrypoint checks confirm refusal status 1, no refused app/server/trash-expiration/banner activity and status 0 on accepted controls; public-debug refusal never starts the mocked sanitizer.
Ruff check, Ruff format --check, deptry and diff whitespace checks pass. Author self-review and independent Astra Ultra read-only support review found no correctness, policy or cleanup issues in the complete task diff. The old debug-refusal shutdown expectation was replaced with no sanitizer construction/start/stop because the guard now executes before startup. The implementation checkpoint retained In Progress status until TASK-121 released the shared Chromium interval for the final gate.

Final validation on implementation 902a986b8c62a5f43ad5bac28a3d174663939a56: pre-commit run -a --hook-stage pre-push passed, including all hygiene, Ruff, deptry and complete pytest coverage checks. Result: 4084 passed, one existing expected failure, no skips; coverage 96.66% exceeds the unchanged 95% branch-inclusive gate. Required headless Chromium coverage was enabled: all 13 launch/close probes passed without timeout. Runtime-only observation preserved the full selection, original timeouts and assertions. The gate exited 0 and no task-owned browser/test processes remained. Closure changes only this ledger; product and test bytes are identical to the validated implementation. TASK-121 remains separate; later coordinated combined validation is still required before any integration.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Both existing serve refusals now exit with status 1. Public-host debug refusal occurs before sanitizer construction, app creation, trash expiration, browser scheduling or the success banner, while the existing host/debug policy and accepted startup/cleanup paths are preserved. Red and green synthetic server/CLI regressions, author review, independent Astra Ultra support review, full browser/coverage gate and normal hooks passed. Preserved on its isolated branch without integration or publication.
<!-- SECTION:FINAL_SUMMARY:END -->
