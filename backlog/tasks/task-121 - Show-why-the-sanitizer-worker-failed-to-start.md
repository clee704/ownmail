---
id: TASK-121
title: Show why the sanitizer worker failed to start
status: To Do
assignee: []
created_date: '2026-09-30 02:12'
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
- [ ] #1 When the worker exits before signaling ready, the refusal names the worker's first error line, such as a missing module or a syntax error
- [ ] #2 A worker that is still running but sends an invalid ready line is reported without waiting on its stderr
- [ ] #3 Tests cover both paths and the full pre-push gate passes
<!-- AC:END -->
