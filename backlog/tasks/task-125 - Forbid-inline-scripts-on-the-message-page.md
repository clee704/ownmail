---
id: TASK-125
title: Forbid inline scripts on the message page
status: In Progress
assignee:
  - '@codex-task125'
created_date: '2026-09-30 03:15'
updated_date: '2026-09-30 16:20'
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
- [x] #1 The message page runs no inline script blocks or inline event-handler attributes, and the existing reader browser tests still pass
- [x] #2 Every message response, with remote content blocked or loaded, sends a Content-Security-Policy whose script-src excludes 'unsafe-inline', and loading remote content still works
- [x] #3 A browser test with a sanitizer stub that lets an inline handler through confirms it does not run, with remote content blocked and loaded
- [ ] #4 The full pre-push gate passes
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 47e54fd653f65a33b394f52207602476dc14126b. Confirmed missing outcome: six inline blocks and 17 handler attributes on the reader, inline scripts allowed in blocked mode and no loaded-mode CSP. Worth doing as a bounded second enforcement layer after sanitization, with no dependency or remote-content policy change. Move parser-time preference restoration, shell/result state, and reader scripts into local static JS at their existing execution positions; carry escaped per-message values on trusted app containers and bind controls only outside message HTML. Set blocked CSP script-src to self and loaded CSP to script-src self. Adapt JSDOM fixtures to load only required local scripts in document order without weakening interaction assertions. Prove actual Flask CSP in Chromium with a retained/triggered benign handler blocked in both modes, retain load/block/trust and remote resource coverage, run focused and full pre-push gates plus mutation checks. Obtain independent review through parent, then hand off clean commits for integration; do not move master.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Ownership confirmed through parent: base/email/result-state templates, new static JS, message response CSP only in web.py, ui-shell/reader-navigation/message-actions harnesses and image-blocking tests. No parser, sanitizer, provider or other web functions. Synthetic fixtures only.

Implemented six parser-order static script extractions and replaced reader/shell inline handlers with listeners scoped to trusted controls. Escaped app data attributes carry sender, message ID, reload URL and auto-scale preference. Every rendered message now restricts script-src to self; loaded policy leaves image/font/media/style requests unchanged. Seven static regressions failed before the change and pass after; both actual-Flask-header retained-handler cases executed the benign handler before and block it after while app controls work. Existing focused checks: 182 non-Chromium checks passed, 20 action tests passed using actual control clicks, and 118 existing affected Chromium checks passed. Initial new-browser fixture mistakenly clicked the intentionally hidden mobile header; corrected it to desktop and both cases passed. A deliberate document-wide binding mutation fails on the spoofed email control; source restored. Ruff and diff checks pass. Independent review and required full pre-push gate remain pending through parent coordination; task stays In Progress.
<!-- SECTION:NOTES:END -->
