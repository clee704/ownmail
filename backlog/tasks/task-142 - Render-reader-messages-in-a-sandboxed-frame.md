---
id: TASK-142
title: Render reader messages in a sandboxed frame
status: In Progress
assignee: []
created_date: '2026-10-11 02:17'
updated_date: '2026-10-16 07:36'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Work on branch feat/reader-message-frame, review base be0f1c4. The branch lands on master only after the maintainer's AC9 check.

1. Design from the current code, and a spike for Space and Shift+Space after clicking in the frame (open risk from TASK-138).
2. Sanitizer output for the frame: unscoped message CSS, viewport units rewritten to a parent-set property, body attributes in the frame document. PDF keeps container scoping.
3. Reader: srcdoc frame in email.html, frame stylesheet, auto-height, fitting, contrast repair, theme and image loading on the frame document without in-frame listeners.
4. Chromium and WebKit tests for AC2 to AC7.
5. Reader print decision (maintainer) and PDF path check.
6. Review and the full pre-push gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-15 maintainer decisions:
- The frame document carries today's container-scoped sanitizer output inside #ownmail-email-content, so the reader and PDF export share one sanitizer output and DOM. Unscoped frame CSS would need a second sanitizer mode and a rework of padding detection, and the common html,body{height:100%} with body padding would grow the frame on every sizing pass. TASK-141 therefore still applies to the reader as well as PDF.
- Printing (AC8): a Print action opens a separate page built from the PDF presentation and prints it there; Cmd+P in the reader prints a note pointing to that action. Cloning the message into the application page at print time was rejected: it puts message CSS back into the application document, and leaves it there if afterprint does not fire.

2026-10-15 Space and Shift+Space (Chromium 145, WebKit 26 through Playwright; synthetic pages): neither engine passes Space from a frame to its parent. Chromium's DefaultSpaceEventHandler (third_party/blink/renderer/core/input/keyboard_event_manager.cc) calls LogicalScroll only, while the arrow handler calls BubblingScroll; WebKit's EventHandler::defaultSpaceEventHandler does not reach the parent frame. Sandbox flags and frame CSS (overflow, overscroll-behavior, scrolling=no) make no difference. Working fix in both engines: once focus has entered the frame, the parent waits until the button is up, the frame selection is collapsed and no frame link has focus-visible, then focuses a parent tabindex=-1 wrapper with preventScroll. Limit: after a drag selection, or while a link has keyboard focus, Space does nothing until the next plain click; PageDown, the arrows and the wheel still scroll. Chromium keeps the frame selection when focus returns to the parent but paints it inactive, and Cmd+C then copies nothing, so focus stays in the frame while text is selected (this corrects TASK-138's note that the selection is dropped). Not checked: a click into the message that activates an inactive browser window (manual, desktop Chrome and Safari), context-menu Copy, VoiceOver, Firefox.

2026-10-15 phase 1 (3536155): the sanitizer rewrites viewport units in message CSS to calc(N * var(--ownmail-vX, 1<unit>)), so the reader can resolve them against its own viewport; the fallback keeps PDF output unchanged.

2026-10-15 progress on the branch:
- fdaa7d5: tests locate message content through frame-aware helpers (message()/messageDocument() in tests/test_email_contrast.py, message_content() in tests/conftest.py, run_contrast_browser(backstop=False)).
- f76a1a8: the reader renders HTML messages in the sandboxed srcdoc frame; plain-text messages stay embedded. The srcdoc attribute is escaped with forceescape (a {% set %} block is Markup and would otherwise be emitted raw; tests/test_message_frame.py fails without it). email-fit.js owns frame layout; email-frame.css holds the frame-side rules and the overflow backstop. Message media queries now evaluate against the frame width, which is at most the reader column. Message form controls no longer pick up application control styles.
- c0ff78c, e03e116: tests/test_message_frame_sizing.py covers AC2 (backstop off) and AC3 (backstop on) in Chromium 145 and WebKit 26. In WebKit, zoomed text keeps a minimum size, so the fit zoom shrinks only for overflow of 2px or less; larger remaining overflow widens the frame and the reader viewport scrolls sideways.
- 793aea8: in WebKit the frame's FontFaceSet reports loaded and fonts.ready resolves while a face is still loading, so layout re-runs from each FontFace.loaded promise instead.
- WebKit failures that predate the branch: label editor tests (TASK-144) and test_message_forms::test_message_links_open_a_new_tab_without_a_referrer.

2026-10-16 progress: 3ebfc0b/9f60717/815e326 (Space focus return in email-reader.js, keyboard and copy tests, sandbox navigation and form tests), e6d0fb9/858e756/2aeca0d (AC6 contrast, backdrop and CSP tests; AC7 isolation tests in tests/test_message_frame_isolation.py, which fail against be0f1c4 in Chromium 6/6 and WebKit 5/6, the WebKit font case passing there because WebKit treats -apple-system as the system-font keyword), 9e0e097 (Print page /print/<email_id> from the PDF presentation; Cmd+P in the reader prints a note for HTML messages; plain text prints as before).

2026-10-16 review (Opus 5.5 and gpt-6-astra, then a separate refutation pass with Chromium and WebKit probes). Findings and proposed dispositions; none fixed yet:
- Fix: img name=fonts or name=scrollingElement survives the sanitizer and clobbers the frame document's fonts/scrollingElement; with fonts the message stays hidden. Drop name on IMG in the sanitizer.
- Fix: Tab into a message without Tab stops (always in WebKit) is trapped by the focus return. Return focus only after pointer interaction, or handle Tab in the parent; keep the Space and Tab-to-link tests passing.
- Fix: widening the frame (actual size, and the widen path when fitting cannot shrink text) also widens percentage-width content, so width:100% plus padding stays clipped. Keep the container at the column width while the frame widens.
- Fix: an absolutely positioned details element that the reader opens is not observed, so its content is clipped. Also observe details elements.
- Fix: the viewport-unit rewrite inside @property initial-value invalidates the registration, in the reader, PDF and Print. Skip the rewrite inside @property.
- Fix: the message()/messageDocument() test helpers fall back to the page; drop the fallback for HTML messages.
- Fix: /print can start the shared sanitizer without its lock after a restart failure; return 503 when the sanitizer is unavailable, as the reader does.
- Record as limits: height and orientation media queries evaluate against the frame, so measuring at height 0 can leave blank space below the message; markup whose height grows through chained height queries needs more than the pass cap and clips.
- Decide: svh/dvh variants collapse onto the vh measurement (not reproducible in Playwright).
Follow-ups to ask the maintainer about before filing: test_pdf_export_cli::test_actual_ctrl_c_stops_renderer_child failed once in a full gate run and passed alone.

Next action: fix the items marked Fix with tests that fail first, re-review the fixes, run the browser suites in Chromium and WebKit and the full pre-push gate, tick AC1-AC8 and AC10 against that evidence, then the maintainer's AC9 check and the desktop check of clicking into the message to activate an inactive window.
<!-- SECTION:NOTES:END -->
