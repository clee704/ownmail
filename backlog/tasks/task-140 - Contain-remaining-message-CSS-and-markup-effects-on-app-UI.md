---
id: TASK-140
title: Contain remaining message CSS and markup effects on app UI
status: Done
assignee: []
created_date: '2026-10-10 08:12'
updated_date: '2026-10-19 03:41'
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
The reader embeds sanitized message HTML in the application page only on the PDF path now: TASK-142 moved the reader to a sandboxed frame, which contains every reader-side effect this task originally listed. PDF export and the reader's Print page (/print/<id>) both render ownmail/templates/pdf.html, which embeds the container-scoped message directly, so the remaining effects act there. Confirmed in Chromium with synthetic messages on 2026-10-18:

- @page: message @page rules follow the template's and win. An unnamed rule changes the page size and margins and adds margin-box text to every page, which can spoof trusted content. Word's @page WordSection1 with div.WordSection1 {page: WordSection1} puts the header alone on an A4 page and the message on Letter pages. The template itself forces A4, so the Print page also locks the print dialog's paper size.
- Fixed positioning repeats message content over every printed page, including the header. Absolutely positioned content covers the header.
- popovertarget and commandfor let a click on the Print page open a message popover or modal dialog in the top layer above the header.
- @property, @keyframes and @font-face have no target in pdf.html: it uses no custom properties or animations, and its font is the generic sans-serif.

Originally filed for the reader as well; narrowed on 2026-10-18 after TASK-142 landed, as doc-4 and the 2026-10-15 note required.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The handling of message @page rules is decided and recorded in the notes: the sanitizer drops them and page declarations, and pdf.html stops forcing a page size; a sanitizer test and a real-renderer test of a Word-style message cover it
- [x] #2 Fixed, absolutely positioned and transformed message content cannot cover the header, note or attachment list on the Print page or in PDF export; a synthetic browser test fails before the fix and passes after it, and long messages still paginate and wide ones still fit
- [x] #3 Message popovers and dialogs cannot be opened through popovertarget or commandfor; the attributes are removed and a synthetic Print page test fails before the fix and passes after it
- [x] #4 A message @font-face named after the PDF template's font cannot change header text; a synthetic browser test guards it and fails when the template uses a named family
- [x] #5 Browser tests run in Chromium and, where installed, WebKit; the engines tested are recorded in the notes
- [x] #6 The full pre-push gate passes with browser tests required
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base 9a43016. Commit to master (no STOP-list area).
1. Sanitizer: drop @page at-rules (any name or nesting) and page declarations in scopeAndSanitizeCSS; reject a leftover @page in isScopedStylesheet; forbid popovertarget, popovertargetaction, commandfor and command.
2. pdf.html: @page keeps only the margin, body width becomes fluid; #ownmail-pdf-body gets contain: layout and overflow-y: clip so it is the containing block for fixed and absolute content and clips vertical overflow. pdf_renderer.js keeps format A4 as the export default.
3. Tests: sanitizer unit tests; Print page browser tests (Chromium, WebKit) for covering content, popovers, dialogs and fonts; extend the real-renderer PDF test with a Word-style @page, a margin box and fixed content.
4. README and notes; review; pre-push gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-10-15: the maintainer scheduled TASK-142 ahead of this task. Before starting, narrow it to the items the frame leaves open, which is the PDF path (the @page decision and fixed-position content over the PDF header).

2026-10-18 decision (maintainer): drop message @page rules. A4 came from TASK-129's first commit with no recorded reason, so the template stops forcing a size as well: the Print page uses the print dialog's paper, and PDF export keeps A4 through pdf_renderer.js format as its one default size. Popovers: AC allows removal; the attributes are removed in the sanitizer, which also affects the reader frame, where no email client feature depends on them.

2026-10-18 implementation:
- Sanitizer: @page at-rules (named, unnamed, nested in @media, with margin boxes) and page declarations are dropped from stylesheets and inline styles; isScopedStylesheet rejects a leftover @page, which catches the comment-trick case. popovertarget, popovertargetaction, commandfor and command are forbidden; the popover attribute stays, so such content stays hidden.
- pdf.html: @page keeps only the 14mm margin; body has no fixed width; #ownmail-pdf-body has contain: layout and overflow-y: clip.
- pdf_renderer.js keeps format A4, but its measuring viewport is now A4's content width (182mm). With the body no longer fixed at 182mm, measuring at 794px fitted wide tables to the wrong width and cut off their right edge.
- Removed the reader-frame popover and dialog tests: they assumed those still open inside the frame, and the attributes that open them are now removed. tests/test_message_print_isolation.py covers the trigger removal on the Print page.
- Template font guard: a message @font-face named after a family the header could use cannot change header text, because pdf.html uses the generic sans-serif, which a quoted family name does not match. The test fails if the template names -apple-system (Chromium) or Arial (WebKit).
- Engines: Print page and frame isolation tests pass in Chromium 145 and WebKit 26 (Playwright); the real-renderer PDF test runs in Chromium.
- Break-to-fail: removing the containment fails the covering-content cases and the PDF fixed-content check; removing the forbidden attributes fails the trigger test; removing the isScopedStylesheet backstop fails the page-rule test; removing the @page and page drops fails the PDF MediaBox check without pdftotext installed and the margin-box check with it.
- Limits: positioned message content that reaches above or below the message box is now clipped. An escaped property name such as p\61 ge survives, because postcss does not decode escapes in property names; it can only add a page break, since no message @page reaches the page. The fitted-width check in the PDF test still needs pdftotext.
<!-- SECTION:NOTES:END -->
