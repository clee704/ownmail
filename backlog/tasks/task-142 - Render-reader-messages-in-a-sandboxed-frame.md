---
id: TASK-142
title: Render reader messages in a sandboxed frame
status: In Progress
assignee: []
created_date: '2026-10-11 02:17'
updated_date: '2026-10-17 05:39'
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
- [x] #1 The reader renders sanitized message HTML in an srcdoc frame with sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" and no allow-scripts; message forms and top-level navigation are blocked and links open in a new tab
- [x] #2 The frame never scrolls internally, vertically or horizontally. The frame document hides its overflow as a backstop. The frame height comes from the content's fractional extent rounded up, is re-checked after it is set, and grows until nothing overflows; sizing re-runs after late image loads, font swaps, viewport width changes, fitting, contrast repair and theme changes. Chromium and WebKit tests with the backstop off find no scrollable overflow for fractional line heights, a fitted (zoomed) wide message, absolutely positioned and transformed content extending below the body, and content that changes after the first measurement
- [x] #3 No message image or text is clipped: Chromium and WebKit tests with the backstop on compare the last element, wide tables, long URLs, late images, viewport-unit content and the AC2 cases with the frame's visible box
- [x] #4 Wheel, PageDown, ArrowDown, Space and Shift+Space over or after clicking in the message scroll the page in Chromium and WebKit, and selecting and copying message text still work
- [x] #5 Wide messages fit as they do today, through email-fit.js applied to the frame document, and viewport units in message CSS resolve against the reader viewport
- [x] #6 Dark mode, contrast repair, image loading and CSP blocking of remote content behave as today, without parent event listeners on nodes inside the frame, which WebKit does not fire
- [x] #7 Message @property, @keyframes, @font-face, fixed positioning, popovers and dialogs cannot affect or cover application UI; Chromium and WebKit tests fail before the change and pass after it
- [x] #8 PDF export keeps direct embedding and container scoping, and the behavior of printing from the reader is decided and recorded
- [ ] #9 Before landing, the maintainer confirms native find in page, swipe, fling and pinch over a long and a wide message in iOS Safari and the Home Screen web app, and no internal scroll or clipping on archive messages that scrolled inside the earlier iframe; the result is recorded in the notes
- [x] #10 The full pre-push gate passes with browser tests required
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

2026-10-16 review (Opus 5.5 and gpt-6-astra, then a separate refutation pass with Chromium and WebKit probes), and two reviews of the fixes (Opus 5.5). Each fix has a test that failed first in the engines where the finding applies:
- b3548b8: /print never starts the shared sanitizer and returns 503 when it is unavailable or returns only the escaped input, so it never serves unsanitized HTML.
- 5efda17: the sanitizer drops name on IMG, so images cannot shadow the frame document's fonts or scrollingElement. The other Document named-property elements (embed, form, iframe, object) are already forbidden tags.
- ee9b7e0: the frame test helpers no longer fall back to the page; message_content(page, plain=True) selects plain-text messages. With HTML embedded in the page, 76 tests fail; no test was passing only through the fallback.
- 1a945b3, 409ae4c: layout pins the frame body to the frame's fractional width, so a widened frame does not widen percentage content. clientWidth rounds, so it is not used.
- ade6188, 647357b: a widened frame copies an opaque content background color onto the frame root, and contrast repair treats overflow text as lying on it.
- 96eddc0: a MutationObserver on open re-runs sizing when a details element toggles; it fires in WebKit.
- e578a38, 1005a1a: after Tab or Shift+Tab focuses the frame document with no focused link, focus moves to #ownmail-email-end or the viewport on the far side, so Space scrolls and the next Tab leaves the message. Links in the frame stay reachable by Tab in Chromium. Anchor tracking (e578a38) was replaced because a click at the same spot defeated it.
- 5efda17, d11da2d: skipping the viewport-unit rewrite inside @property was reverted. The unrewritten unit resolved against the content-sized frame, so initial-value: 100vh clipped. The rewritten rule is invalid and the browser drops the registration, which leaves the box at its natural height.

Limits:
- Height and orientation media queries evaluate against the frame, so measuring at height 0 can leave blank space below the message; markup whose height grows through chained height queries needs more than the pass cap and clips.
- svh and dvh collapse onto the vh measurement. Accepted as a limit: they differ only by the iOS toolbar height, Playwright cannot reproduce it, and the AC9 check covers iOS.
- A property registered with a viewport unit in an @property descriptor stays unregistered.
- In a widened frame only an opaque background color continues past the column; background images and semi-transparent or non-sRGB colors stop at the column edge.
- With a column fraction under 0.5 the frame viewport rounds down, and 100%-width content can end about 0.2px past it, inside the frame's visible box (not shown to be visible).
- #ownmail-email-end is an empty tabindex=-1 element; what a screen reader announces there is unchecked, with VoiceOver in general.

Gate evidence at 647357b: the pre-push gate with OWNMAIL_REQUIRE_BROWSER_TESTS=1 passes in Chromium. The full suite in WebKit fails only the four label editor tests (TASK-144); test_message_forms::test_message_links_open_a_new_tab_without_a_referrer now passes in WebKit. Under heavy load from parallel browser probes, the test_pdf_export Ctrl-C tests and test_download_progress::test_interrupt_flushes_current_counts_without_message_errors[downloading] timed out or miscounted in both engines and passed alone. Filed with the earlier test_pdf_export_cli Ctrl-C failure as TASK-147.

Next action: the maintainer's AC9 check on iOS Safari and the Home Screen web app, and the desktop check of clicking into the message to activate an inactive Chrome or Safari window; then land the branch on master.

2026-10-16 AC9 preparation: check 9 in docs/home-screen-validation.md lists the frame checks (swipe, fling, pinch, Find on Page, end and right edge visible, and archive messages that scrolled inside the earlier iframe). The fixture recipe adds 047, a message with a 1200px-wide table; it imports 47 messages, and 047 renders in the sandboxed frame through the real sanitizer on this branch. No simulator pre-check of this branch was run. Next action unchanged: the maintainer runs check 9 on an iPhone in Safari and the Home Screen app, and the results are recorded here.
<!-- SECTION:NOTES:END -->
