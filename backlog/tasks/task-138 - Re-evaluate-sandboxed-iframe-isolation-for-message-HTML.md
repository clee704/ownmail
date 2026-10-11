---
id: TASK-138
title: Re-evaluate sandboxed iframe isolation for message HTML
status: In Progress
assignee: []
created_date: '2026-10-10 05:41'
updated_date: '2026-10-11 02:17'
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
- [x] #1 Each earlier reason listed above is re-checked against the allow-same-origin, no-scripts variant with a synthetic prototype or cited evidence, naming the browsers tested.
- [ ] #2 CSP inheritance for srcdoc, print and PDF export, and Home Screen web app behavior are each checked, or recorded as unaffected with the reason.
- [x] #3 A recommendation and its rationale are recorded in this task's notes; any implementation work is filed as a separate task.
- [x] #4 No production code, template or stylesheet changes in this task.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-10 spike results. Variant: srcdoc frame with sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" and no allow-scripts; comparison point: the same sandbox without allow-same-origin. Engines: Chromium 145.0.7632.6 and WebKit 26.0 through Playwright 1.58.0 (the copy in ownmail/sanitizer/node_modules) on macOS; Firefox was not installed. Synthetic prototypes only, kept outside the repository; the parent pages sent IMAGE_BLOCKING_CSP or MESSAGE_CSP copied from ownmail/web.py.

Earlier reasons:
1. Find in page: unverified. window.find in the parent does not search frame documents in either engine, and headless Playwright cannot drive the native find bar. Chromium's find bar searches every frame (content/browser/find_request_manager.cc); Safari is unverified, and 55d2fc8 does not say which browser failed. Needs a manual find-bar check in desktop Chrome, Safari, and iOS Safari and the Home Screen app.
2. Frame height: works in both engines with about 30 lines (set the frame height to 0, read the frame root's scrollHeight, re-run from a parent ResizeObserver). Height stayed stable for an image loading late, height:100% html and body, and collapsing margins, with no feedback loop. Viewport units resolve against the frame, so min-height:100vh content was clipped; the sanitizer would rewrite vh, svh, lvh, dvh, vmin and vmax to a parent-set custom property (estimated 30 to 50 lines in worker.js, on cssTokens).
3. Frame styling: works in both engines. A stylesheet linked from srcdoc loads under 'self', the parent can toggle the dark-mode class on the frame root, and it can rewrite message dark-mode media rules as applyEmailMediaTheme does. The 15 #ownmail-email-content rules in style.css would move to a frame stylesheet.
4. Links: work in both engines. worker.js already adds target=_blank, so no base element is needed. Popups open and escape the sandbox; target=_top navigation and form submission are blocked without a request.
5. Parent access: the parent can read contentDocument, computed styles and geometry, swap image src and edit stylesheets in both engines. In WebKit, listeners the parent attaches to nodes inside the frame (capturing load, click, the onload property) never fire; ResizeObserver, contentDocument.fonts.ready and the iframe element's own load event do. email-fit.js (line 42) and email-contrast.js (lines 41, 212-213) need those substitutions, about 10 to 20 lines in email-contrast.js.

Other checks:
- CSP: a srcdoc frame inherits the reader's policy in both engines. Under IMAGE_BLOCKING_CSP no remote image, background or font request reached the server from the page, the variant frame or the opaque frame; under MESSAGE_CSP and with no policy all nine arrived. default-src did not block the srcdoc frames themselves. Spec: HTML policy containers.
- Print and PDF: Chromium page.pdf with the pdf_renderer.js options ignores a message @page inside a frame (A4 instead of the message's A5), cuts lines at page edges, and with JavaScript off, as pdf_renderer.js runs, printed only 6 of 120 lines of a tall frame. PDF export should keep direct embedding with _extract_body_content and container scoping. Printing from the reader needs a decision: accept cut lines, or add a per-message PDF action (about 40 to 80 lines). WebKit printing could not be tested through Playwright.
- Home Screen web app: unverified; Playwright cannot emulate iOS standalone mode. No script treats standalone mode specially. Needs a manual check of frame height after images load, long-message scrolling, link opening and find.

TASK-140 effects: with direct embedding as the control, @property on an application variable, @keyframes ownmail-spin, @font-face with the UI font name, position:fixed, popovertarget popovers and commandfor modal dialogs each reached application UI. Inside the frame each stayed within the frame in both engines, and the application stayed clickable under a modal dialog. A message @page changed the PDF page size with direct embedding and was ignored in the frame. TASK-141: @scope rules work unmodified inside the frame.

Recommendation (conditional on the find-bar check): render reader messages in the allow-same-origin, no-scripts frame, and keep PDF export on direct embedding with container scoping. Rationale: the frame contains every application-facing TASK-140 effect without per-feature rules, inherits the reader CSP, blocks forms and top-level navigation while links still work, and needs about 30 lines of height code where the earlier frame needed about 150. Costs: the viewport-unit rewrite, the WebKit listener substitutions, reader print quality, and two render paths. If the frame lands, TASK-140 narrows to the PDF path (the @page decision, and fixed-position content over the PDF header, by inspection) and TASK-141 applies only to PDF.

Implementation outline for the follow-up task: an iframe in email.html whose srcdoc carries the sanitized document, the frame stylesheet and the body attributes; the frame stylesheet; an unscoped sanitizer mode with the viewport-unit rewrite; auto-height and zoom in email-fit.js; email-contrast.js and applyEmailTheme pointed at the frame document with WebKit-safe listeners; a reader print decision; Chromium and WebKit tests.

Next action: the maintainer checks the native find bar and the Home Screen app against a synthetic page with text inside such a frame. Then record the result, finalize the recommendation, and file the implementation task.

2026-10-10: the maintainer confirmed that native find in page finds text inside the frame on the synthetic page. New requirement from the maintainer: the frame must behave like a normal element, with no internal scroll; the earlier iframe also had scrolling problems. Checking scroll behavior before finalizing the recommendation.

2026-10-10: the maintainer added that the frame must not clip images or text. Hiding overflow passes only if all content stays fully visible.

2026-10-10 scroll and clipping results (Chromium 145 and WebKit 26 through Playwright; synthetic pages). Iframe-era history shows height problems only (e83c604 late images, 9602cb3 onload timing and a scrollHeight feedback loop); no commit mentions wheel, keyboard, touch or horizontal scrolling. With an auto-height frame: wheel over the frame scrolls the page at its top, middle and end in both engines; no internal overflow after a late image, a font swap, a width change, or a page without a doctype; PageDown and ArrowDown after clicking in the message scroll the page. Failures and fixes: auto-height must attach to the srcdoc document, not the initial about:blank document Chromium exposes, or the frame stays at 8px or 150px; vh-sized content clips until the sanitizer rewrites viewport units; an unfitted 900px table scrolls and clips in a 375px viewport and passes once email-fit.js zoom or an actual-size wrapper is applied through contentDocument; long URLs pass with overflow-wrap:anywhere. Space and Shift+Space after clicking in the message do not scroll the page in either engine: a parent keydown forwarder works only in Chromium, and returning focus to the parent works in both but drops the frame selection in Chromium. overflow:hidden and scrolling=no add nothing once the frame fits, and overflow:hidden clipped 525px of a 900px table, so it fails the no-clipping requirement. Emulated touch scrolling passed in Chromium; iOS swipe, fling and pinch are unverified because Playwright WebKit has no swipe API. Trackpad momentum and Firefox were not tested.

2026-10-10 recommendation: render reader messages in the allow-same-origin, no-scripts frame and keep PDF export on direct embedding with container scoping; filed as TASK-142 with the no-internal-scroll and no-clipping requirements as acceptance criteria. Open risks: Space and Shift+Space after clicking in the message have no cross-engine fix yet, and iOS touch scrolling and the Home Screen web app are unverified. Next action: the maintainer checks swipe, fling, pinch, a wide message and find on an iPhone in Safari and the Home Screen app against a synthetic frame page; then check AC2 and close this task.
<!-- SECTION:NOTES:END -->
