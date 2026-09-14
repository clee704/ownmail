---
id: TASK-81
title: Run downloads and configure a schedule from the web interface
status: In Progress
assignee: []
created_date: '2026-09-14 06:59'
updated_date: '2026-09-14 07:11'
labels: []
dependencies: []
type: feature
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Allow archive operators to start the existing download command and configure periodic downloads from web Settings, so keeping the archive current does not require repeated terminal commands.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings can start a download without blocking browsing and show its running and completion or failure state.
- [x] #2 Operators can save or disable a periodic interval; it survives server restart and runs while the browser is closed.
- [x] #3 Web and CLI downloads cannot overlap for the same archive; server shutdown and development reload clean up background work.
- [x] #4 Regression tests, browser verification, and the full pre-push checks pass; usage and operational limits are documented.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Reuse the existing command in a managed subprocess. Add a cross-process archive lock and accurate CLI outcomes, a server scheduler, and Settings controls with persisted intervals. Verify scheduling, errors, restart, and UI behavior on synthetic data. Review the complete change before committing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
User-directed feature; the unrelated repository-governance task remains In Progress. Periodic downloads default to Off. Existing credential, OAuth, archive file, and database behavior remains in place.

CLI outcomes and archive locking, server scheduling, and web routes are implemented. Targeted tests verify real competing CLI processes, config persistence across app recreation, interval disabling, failure responses, same-origin request checks, and reloader ownership. Browser verification, independent review, and the full pre-push gate remain pending.

Full pre-push checks pass with browser tests required. Real Chromium tests cover download feedback, duplicate clicks, polling recovery, unsaved settings, schedule saves and failures, and phone layout; desktop and phone screenshots were inspected. Independent review identified config-write races and detached children surviving SIGTERM. Shared config locking and atomic replacement fix the races; scoped signal handling stops and reaps downloads on server shutdown. Both fixes have concurrency or real-process regressions. Mutation checks confirmed the tests detect missing persistence, locking, UI draft protection, and shutdown handling. No runtime dependencies, credential or OAuth behavior, database schema, or archive deletion behavior changed.
<!-- SECTION:NOTES:END -->
