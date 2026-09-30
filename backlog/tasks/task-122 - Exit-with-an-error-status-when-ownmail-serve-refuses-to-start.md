---
id: TASK-122
title: Exit with an error status when ownmail serve refuses to start
status: In Progress
assignee:
  - '@codex-ic2'
created_date: '2026-09-30 02:12'
updated_date: '2026-09-30 13:10'
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
- [ ] #1 Each refusal exits with a non-zero status
- [ ] #2 The --debug and non-localhost refusal happens before create_app and before the banner
- [ ] #3 Tests cover both refusals and the full pre-push gate passes
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
<!-- SECTION:NOTES:END -->
