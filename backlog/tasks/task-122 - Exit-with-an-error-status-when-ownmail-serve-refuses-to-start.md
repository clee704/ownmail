---
id: TASK-122
title: Exit with an error status when ownmail serve refuses to start
status: To Do
assignee: []
created_date: '2026-09-30 02:12'
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
