---
id: TASK-139
title: Keep message HTML from submitting forms
status: Done
assignee: []
created_date: '2026-10-10 06:17'
updated_date: '2026-10-10 07:37'
labels:
  - security
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - ownmail/static/app-shell.js
  - tests/test_message_forms.py
priority: high
type: bug
ordinal: 9935
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The sanitizer (ownmail/sanitizer/worker.js) keeps `<form>` elements and their submit controls, and only forces `target="_blank" rel="noopener noreferrer"` on forms. A message containing `<form method="post" action="/empty-trash"><button>Read</button></form>` renders a control that submits to the application's own state-changing routes with one click; /empty-trash permanently deletes every message in the local bin. ownmail/static/app-shell.js also attaches its loading overlay to every form on the page, including forms in message content.

Whether the browser sends a matching Origin for such a submission varies by browser. TASK-137 adds CSRF tokens, but message content should not be able to submit forms at all.

Neutralize forms in the sanitizer: unwrap `<form>` so its children stay as non-form content, and remove the `formaction`, `formmethod`, `formtarget`, `formenctype`, `formnovalidate` and `form` attributes from every element. Check retained markup for other ways to send requests to the application.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The sanitizer unwraps `<form>` elements and keeps their content, and removes the formaction, formmethod, formtarget, formenctype, formnovalidate and form attributes from every element.
- [x] #2 Synthetic sanitizer tests cover a POST form, a GET form, formaction on a button and a form attribute that names an id; they fail before the fix and pass after it.
- [x] #3 A browser test with every request intercepted clicks the former submit control in the reader and asserts that no request is sent and the loading overlay stays hidden.
- [x] #4 Other request vectors in retained markup are checked, and the result is recorded in the implementation notes.
- [x] #5 User documentation that describes message rendering states that message forms cannot be submitted.
- [x] #6 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The sanitizer now lists form in FORBID_TAGS, so DOMPurify unwraps it and keeps its children (KEEP_CONTENT is on by default). form, formaction, formenctype, formmethod, formnovalidate and formtarget are in FORBID_ATTR. DOMPurify 3.4.16 already dropped every one of these attributes except formaction through its default allowlist; listing them keeps that independent of the defaults and of ADD_ATTR. The hook that forced target and rel on forms now applies to links and image-map areas. An `<area href>` in a message used to navigate the reader tab and send a referrer, because DOMPurify drops target from area; the hook sets target=_blank and rel=noopener noreferrer after sanitizing, as for `<a>`. test_allows_form_elements asserted the old behavior and was replaced.

With forms unwrapped, app-shell.js finds no message form to attach its submit overlay to (it also skips forms inside the message since TASK-133); the browser test confirms the overlay stays hidden. The forged editor markup in tests/test_label_editor.py is inserted without the sanitizer, so those tests still check the scripts on their own.

Other request vectors checked against the sanitizer output:
- isindex, meta (including http-equiv refresh), base, iframe, frame, object, embed, svg and math are removed.
- link is kept only as a stylesheet from a trusted font host; prefetch, preload and other relations are removed.
- The ping attribute on a and area is removed by the default allowlist.
- input type=image, img, media and background URLs can send GET requests. Remote ones are covered by remote content blocking; local ones reach only GET routes, which change no state.
- A dialog form (method=dialog) is unwrapped with the other forms.
- popovertarget and commandfor/command are kept. They send no requests, and the application page has no popover or dialog elements for them to target. They can still open popovers or modal dialogs inside the message itself, which is a container-isolation question for TASK-138.
- The reader CSP has no form-action directive. form-action 'self' would not stop same-origin submissions, so the sanitizer fix is the control.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Message HTML can no longer submit forms. The sanitizer unwraps form elements and removes form-related attributes from every element, so message controls have no form owner and cannot reach state-changing routes or trigger the loading overlay. Sanitizer tests cover POST and GET forms, formaction on a button and a form attribute naming an id; a browser test with every request intercepted clicks each former control and presses Enter in a field, and asserts that no request or popup appears. Image-map areas open a new tab without a referrer, like links; a browser test clicks both. README and the setup guide note that message form controls cannot submit.
<!-- SECTION:FINAL_SUMMARY:END -->
