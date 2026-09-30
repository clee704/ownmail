---
id: TASK-125
title: Forbid inline scripts on the message page
status: To Do
assignee: []
created_date: '2026-09-30 03:15'
labels:
  - ui
dependencies: []
priority: medium
type: enhancement
ordinal: 9800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Message responses rely on DOMPurify and body extraction alone to keep a message's scripts from running. The blocking policy (IMAGE_BLOCKING_CSP in ownmail/web.py) allows script-src 'unsafe-inline' because the reader page uses inline scripts and event-handler attributes, and a message shown with remote content loaded carries no Content-Security-Policy at all. This is why the TASK-120 handler ran in both modes.

The message page has six inline script blocks (base.html, email.html and the included _result_state.html) and 17 inline onclick attributes (base.html and email.html). Other pages share base.html. Moving these to static files and event listeners would let every message response send a script-src without 'unsafe-inline', blocked or loaded, so a future sanitizer or extraction bug cannot run script. The policy for loaded messages must still allow the remote images, fonts and media the reader loads on request. Suggested in TASK-120's description; filed from its audit.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The message page runs no inline script blocks or inline event-handler attributes, and the existing reader browser tests still pass
- [ ] #2 Every message response, with remote content blocked or loaded, sends a Content-Security-Policy whose script-src excludes 'unsafe-inline', and loading remote content still works
- [ ] #3 A browser test with a sanitizer stub that lets an inline handler through confirms it does not run, with remote content blocked and loaded
- [ ] #4 The full pre-push gate passes
<!-- AC:END -->
