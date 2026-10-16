---
id: TASK-142
title: Render reader messages in a sandboxed frame
status: To Do
assignee: []
created_date: '2026-10-11 02:17'
labels:
  - security
dependencies:
  - TASK-138
references:
  - ownmail/templates/email.html
  - ownmail/static/email-fit.js
  - ownmail/static/email-contrast.js
  - ownmail/static/email-reader.js
  - ownmail/sanitizer/worker.js
priority: medium
type: feature
ordinal: 9945
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-138 found that an srcdoc iframe with sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" and no allow-scripts contains the message CSS and markup effects that still reach application UI (TASK-140), inherits the reader CSP, and blocks forms and top-level navigation. Parent scripts keep access through contentDocument for fitting, contrast repair, theme switching and auto-height. TASK-138's notes have the prototypes' results, the WebKit listener limitation, and the scroll and clipping checks.

The frame must behave like a normal element: no internal scroll and no clipped images or text. Internal scroll is the worse failure, because a message that scrolls inside the frame makes the reader unusable, so the frame document hides its overflow as a backstop (maintainer decision, 2026-10-11). Sizing must still show all content on its own, so the no-scroll tests run with the backstop off and cannot pass because of it. PDF export stays on direct embedding with container scoping, because Chromium cuts frames at page edges and the PDF renderer runs without JavaScript; TASK-140 and TASK-141 then apply to the PDF path only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The reader renders sanitized message HTML in an srcdoc frame with sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" and no allow-scripts; message forms and top-level navigation are blocked and links open in a new tab
- [ ] #2 The frame never scrolls internally, vertically or horizontally. The frame document hides its overflow as a backstop. The frame height comes from the content's fractional extent rounded up, is re-checked after it is set, and grows until nothing overflows; sizing re-runs after late image loads, font swaps, viewport width changes, fitting, contrast repair and theme changes. Chromium and WebKit tests with the backstop off find no scrollable overflow for fractional line heights, a fitted (zoomed) wide message, absolutely positioned and transformed content extending below the body, and content that changes after the first measurement
- [ ] #3 No message image or text is clipped: Chromium and WebKit tests with the backstop on compare the last element, wide tables, long URLs, late images, viewport-unit content and the AC2 cases with the frame's visible box
- [ ] #4 Wheel, PageDown, ArrowDown, Space and Shift+Space over or after clicking in the message scroll the page in Chromium and WebKit, and selecting and copying message text still work
- [ ] #5 Wide messages fit as they do today, through email-fit.js applied to the frame document, and viewport units in message CSS resolve against the reader viewport
- [ ] #6 Dark mode, contrast repair, image loading and CSP blocking of remote content behave as today, without parent event listeners on nodes inside the frame, which WebKit does not fire
- [ ] #7 Message @property, @keyframes, @font-face, fixed positioning, popovers and dialogs cannot affect or cover application UI; Chromium and WebKit tests fail before the change and pass after it
- [ ] #8 PDF export keeps direct embedding and container scoping, and the behavior of printing from the reader is decided and recorded
- [ ] #9 Before landing, the maintainer confirms native find in page, swipe, fling and pinch over a long and a wide message in iOS Safari and the Home Screen web app, and no internal scroll or clipping on archive messages that scrolled inside the earlier iframe; the result is recorded in the notes
- [ ] #10 The full pre-push gate passes with browser tests required
<!-- AC:END -->
