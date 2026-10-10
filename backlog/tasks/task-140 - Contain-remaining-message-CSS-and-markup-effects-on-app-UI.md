---
id: TASK-140
title: Contain remaining message CSS and markup effects on app UI
status: To Do
assignee: []
created_date: '2026-10-10 08:12'
updated_date: '2026-10-10 08:12'
labels:
  - security
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - ownmail/templates/email.html
  - ownmail/templates/pdf.html
  - ownmail/static/email-reader.js
priority: medium
type: bug
ordinal: 9950
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The reader embeds sanitized message HTML in the application page. TASK-131 confines every message selector and @scope root to #ownmail-email-content, and TASK-139 stops message forms from submitting. The effects below still reach application UI because they act through global names, the page box or the top layer rather than selectors. Each was confirmed in Chromium with a synthetic page unless noted. TASK-131's implementation notes have the original findings.

- @property (highest impact): a message that registers an application custom property such as `--ownmail-text` with `inherits: false` recolors application UI. Likely fix: drop message @property rules.
- @keyframes: a message `@keyframes ownmail-spin` replaces the loading spinner animation. Likely fix: drop or rename message keyframes in the `ownmail-` namespace, comparing unescaped names.
- @font-face: a family named like the first available UI font (-apple-system on macOS; Segoe UI or Roboto elsewhere, unverified) replaces the application font, which allows glyph substitution in trusted text such as the sender line. Needs a generic-only UI font stack, or renaming message families and every reference to them.
- @page (by inspection, not rendered): PDF export prints with preferCSSPageSize, and message @page rules follow the template's, so they can change page size and margins and add margin-box text. Word-generated messages commonly carry `@page WordSection1`, so dropping @page changes their PDFs and needs a decision.
- position: fixed (by inspection): #ownmail-email-viewport has no containment, so scoped fixed-position message content can cover application UI.
- popovertarget and commandfor survive sanitization. The application page has no popover or dialog elements for them to target today, but a message can open its own popover or modal dialog in the top layer above application UI, which allows spoofing.

TASK-138 evaluates a sandboxed frame that would contain all of these together. If the maintainer schedules a frame ahead of this task, narrow this task to the items the frame leaves open before starting.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Message @property rules cannot change application custom properties; a synthetic browser test that registers an application property fails before the fix and passes after it.
- [ ] #2 Message @keyframes cannot replace application animations, including names written with CSS escapes; a synthetic browser test fails before the fix and passes after it.
- [ ] #3 Message @font-face rules cannot replace the font of application UI text; a synthetic browser test fails before the fix and passes after it.
- [ ] #4 The handling of message @page rules in PDF export is decided and recorded in the notes, with a synthetic test for the chosen behavior.
- [ ] #5 Fixed-position message content cannot cover reader controls or other application UI; a synthetic browser test fails before the fix and passes after it.
- [ ] #6 Message popovers and dialogs opened through popovertarget or commandfor cannot cover application UI, or the attributes are removed; a synthetic browser test fails before the fix and passes after it.
- [ ] #7 Browser tests run in Chromium and, where installed, WebKit; the engines tested are recorded in the notes.
- [ ] #8 The full pre-push gate passes with browser tests required.
<!-- AC:END -->
