---
id: TASK-133
title: Keep message markup from driving the label editor
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 07:35'
labels:
  - security
dependencies: []
references:
  - ownmail/static/label-editor.js
  - ownmail/static/app-shell.js
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
- [x] #1 The reader page does not load label-editor.js when the label editor is not rendered.
- [x] #2 label-editor.js binds only controls outside #ownmail-email-content and sends requests only to the labels route of the message being read; sender markup that reuses every editor ID cannot cause a request.
- [x] #3 A browser regression renders a cached view whose synthetic message supplies every editor ID with data-url="/empty-trash" and an enabled submit button, clicks it, and asserts no POST is sent; an archive-view case asserts the real editor still loads and saves.
- [x] #4 Reader scripts that run after the message body are checked for document-wide ID lookups that some template branch leaves unresolved, and the result is recorded in the notes.
- [x] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Other reader scripts that run after the message body (email-reader.js, email-fit.js, email-contrast.js) look up IDs that, by code reading, are rendered before the body in every template branch. Confirm this in AC #4 rather than assuming it.

A sandboxed message iframe would hide message elements from document.getElementById and remove this class of gadget; see the isolation notes in TASK-131. The point fix is recommended for now.

Fix: email.html loads label-editor.js only with the editor and no longer renders data-url. The script takes its trigger from #ownmail-reader-actions, binds only an editor outside #ownmail-email-content, reads every control inside that editor, and builds the request URL from the reader's email ID.

Regression (tests/test_label_editor.py): synthetic markup repeating all eleven editor IDs, with data-url="/empty-trash" and an enabled submit button. Before the fix, clicking it sent POST /empty-trash in a cached view, with the script injected into a cached view, and in an archive view without the real editor section. After the fix none sends a request, and an archive view with the same markup still loads and saves only through /labels/<id>. The harness now routes the whole browser context, so message form popups stay offline.

AC #4 audit of reader scripts that run after the body:
- email-fit.js, email-reader.js and email-contrast.js look up only IDs rendered before the body in every branch that loads them. The fit control shares the body_html condition, and the active status panel and its close button share the toggle's active condition.
- email-remote-content.js runs before the body. Its action-time lookups of menu-trust-sender and menu-untrust-sender are rendered in the same branch as the button that calls them.
- message-actions.js runs in base.html before the content block. At action time it disables and then restores every [data-message-action], including message elements; that sends no request.
- app-shell.js looks up base-layout IDs that precede the content, but it also bound the loading overlay to every `form` and every `.ownmail-pagination a` in the document, so a message form or a message link with that class could raise the overlay and, by code reading, a false connection error after 30 seconds. No request was possible. No template renders `.ownmail-pagination` any more, so that binding is removed; the submit binding skips forms inside #ownmail-email-content. tests/test_label_editor.py checks both in a browser.
- result-state.js was affected: no reader branch renders ownmail-email-list or ownmail-reader-unavailable, so message HTML could bind the list click handler (position save and loading overlay) or clear the reading checkpoint. No request was possible. It now ignores both IDs on reader pages; tests/test_reader_navigation.py covers this.

Not changed: the sanitizer still keeps id and data-* attributes. Stripping reserved ownmail- IDs would cover only part of the reader's IDs (search-input, menu-* and load-images-btn lack the prefix) and none of its class-based lookups. The fixes above do not depend on it, and the isolation option in TASK-131 would remove the class.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
label-editor.js binds only the editor outside the message and posts only to the current message's labels route. The reader loads it only when the editor is rendered. result-state.js ignores result-list and unavailable-page IDs on reader pages, and app-shell.js binds its loading overlay only to the app's own forms. Browser and script-level regressions fail against the previous code.
<!-- SECTION:FINAL_SUMMARY:END -->
