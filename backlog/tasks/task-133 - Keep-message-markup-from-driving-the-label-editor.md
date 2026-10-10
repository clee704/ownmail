---
id: TASK-133
title: Keep message markup from driving the label editor
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
labels:
  - security
dependencies: []
references:
  - ownmail/static/label-editor.js
  - ownmail/templates/email.html
  - tests/test_label_editor.py
priority: high
type: bug
ordinal: 9890
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
label-editor.js (ownmail/static) finds its controls with document-wide getElementById and sends the label fetch and the save POST to `editor.dataset.url`. When `cached_view` is set, templates/email.html omits the label editor section and the Edit labels trigger, but still loads label-editor.js after the message body. The sanitizer keeps `id` and `data-*` attributes, so a cached message can supply every control ID the script reads (ownmail-label-editor with `data-url="/empty-trash"`, ownmail-edit-labels, ownmail-label-items, ownmail-label-status, ownmail-label-input, ownmail-label-add, ownmail-label-save, ownmail-label-close, ownmail-label-form) with an enabled submit button. One click on that button makes the trusted script POST `{"labels": []}` as JSON to /empty-trash with a matching Origin. csrf_check accepts it, and the server empties the bin before the script fails to decode the redirect response.

In archive views the real editor precedes the message, so getElementById returns it and this chain does not apply. This is a user-assisted request gadget; no zero-click path or script execution has been shown.

Load label-editor.js only when the editor is rendered. Resolve its controls inside the trusted editor and reader-actions containers, which precede and exclude the message, as email-reader.js already does for reader actions. Send requests only to the labels route of the message being read.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The reader page does not load label-editor.js when the label editor is not rendered.
- [ ] #2 label-editor.js binds only controls outside #ownmail-email-content and sends requests only to the labels route of the message being read; sender markup that reuses every editor ID cannot cause a request.
- [ ] #3 A browser regression renders a cached view whose synthetic message supplies every editor ID with data-url="/empty-trash" and an enabled submit button, clicks it, and asserts no POST is sent; an archive-view case asserts the real editor still loads and saves.
- [ ] #4 Reader scripts that run after the message body are checked for document-wide ID lookups that some template branch leaves unresolved, and the result is recorded in the notes.
- [ ] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Other reader scripts that run after the message body (email-reader.js, email-fit.js, email-contrast.js) look up IDs that, by code reading, are rendered before the body in every template branch. Confirm this in AC #4 rather than assuming it.

A sandboxed message iframe would hide message elements from document.getElementById and remove this class of gadget; see the isolation notes in TASK-131. The point fix is recommended for now.
<!-- SECTION:NOTES:END -->
