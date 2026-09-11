---
id: TASK-41
title: Reload the web server during development
status: In Progress
assignee: []
created_date: '2026-09-11 10:50'
updated_date: '2026-09-11 10:54'
labels: []
dependencies: []
priority: medium
type: feature
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Add ownmail serve --reload so Python source changes restart the server without enabling the interactive debugger. Preserve existing debug mode and allow template edits to appear on refresh.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The serve CLI accepts --reload and enables source reloading without enabling debug mode.
- [x] #2 Reloaded serving processes do not open extra browser tabs; --no-browser still suppresses browser launch.
- [x] #3 Template edits are visible on refresh in reload mode, and a source edit restarts a running test server.
- [x] #4 Help and developer documentation describe the flag; regression tests and full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added --reload independently of --debug using the existing Flask/Werkzeug reloader. Reload mode also refreshes Jinja templates. Browser launch runs only in the supervisor, so child restarts do not open more tabs. Regression checks cover CLI defaults and dispatch, debug/reload combinations, public-host reload without the debugger, template refresh, and browser launch across reloader processes. New checks reproduced the missing behavior before implementation; all focused checks now pass.

A subprocess smoke test against a copied package and new empty archive confirmed that template edits appear on the next request and Python edits restart the server and serve updated code, with debug mode off throughout. Full pre-push checks passed. Independent review found no in-scope issues.
<!-- SECTION:NOTES:END -->
