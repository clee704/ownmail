---
id: TASK-138
title: Re-evaluate sandboxed iframe isolation for message HTML
status: To Do
assignee: []
created_date: '2026-10-10 05:41'
labels:
  - security
dependencies: []
references:
  - ownmail/templates/email.html
  - ownmail/sanitizer/worker.js
  - ownmail/web.py
  - ownmail/static/email-reader.js
priority: medium
type: spike
ordinal: 9940
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The reader embeds sanitized message HTML in the application document and keeps message CSS inside it by scoping selectors under #ownmail-email-content (scopeAndSanitizeCSS and scopeQualifiedBodySelector in ownmail/sanitizer/worker.js). Message CSS and markup have escaped that boundary: TASK-131 and TASK-134 are point fixes for scope escapes, and TASK-133 fixes an element ID collision that lets message markup drive the label editor. They follow earlier fixes in the same area (TASK-56, TASK-119, TASK-120, TASK-124). TASK-131's implementation notes assess frame isolation as the structural alternative.

Re-evaluate rendering the message in a sandboxed frame.

## Earlier reasons for leaving the iframe

From b049db0 to 55d2fc8 the reader rendered messages in `<iframe sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" srcdoc="...">`. 55d2fc8 replaced it with direct embedding and container scoping. No decision record exists; the reasons come from that commit and the iframe-era fixes:

1. Find in page: 55d2fc8 states native browser search (Ctrl+F) as the reason for the change.
2. Frame height: following content height took about 150 lines of resize code (ResizeObserver, re-measuring after each image load, timed fallbacks), with fixes for resize feedback loops and frames that did not grow after images loaded (e83c604, 9602cb3).
3. Frame styling: base font, margins and dark-mode rules were injected into the frame document separately from the application stylesheet (09ea4e1, cf34c66, 91a24d8).
4. Links: links needed `<base target="_blank">` to avoid navigating inside the frame, and allow-popups with allow-popups-to-escape-sandbox to open at all (d60bbe8, 5f43f2f).
5. Parent access: image loading reached into the frame document (b049db0); direct embedding let it query the container instead.

9d58922 then removed the README claim that the iframe sandbox protected users without the sanitizer; the sanitizer has been required since.

## Variant to evaluate

A srcdoc frame whose `sandbox` allows same-origin but not scripts:

- Message scripts cannot run. Parent scripts keep DOM access, so fit (email-fit.js), contrast repair (email-contrast.js), theme switching (applyEmailTheme in email-reader.js) and auto-height can operate on the frame document.
- The message gets its own CSS cascade and ID namespace, so container scoping and the body-attribute transfer in _extract_body_content could be retired rather than extended.
- Forms stay blocked unless allow-forms is added.
- Links need allow-popups and allow-popups-to-escape-sandbox.

The fully opaque frame described in TASK-131's notes is the comparison point.

Also check:

- CSP: whether a srcdoc document inherits the reader's Content-Security-Policy, which blocks remote content today.
- Print and PDF export: the reader's print stylesheet, and pdf_export.py, which shares _extract_body_content and container scoping through templates/pdf.html.
- Home Screen web app: frame sizing, scrolling and link opening in standalone mode.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each earlier reason listed above is re-checked against the allow-same-origin, no-scripts variant with a synthetic prototype or cited evidence, naming the browsers tested.
- [ ] #2 CSP inheritance for srcdoc, print and PDF export, and Home Screen web app behavior are each checked, or recorded as unaffected with the reason.
- [ ] #3 A recommendation and its rationale are recorded in this task's notes; any implementation work is filed as a separate task.
- [ ] #4 No production code, template or stylesheet changes in this task.
<!-- AC:END -->
