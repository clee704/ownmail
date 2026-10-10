---
id: TASK-131
title: Scope message CSS selectors that name the reader container
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 06:31'
labels:
  - security
dependencies: []
references:
  - ownmail/sanitizer/worker.js
  - tests/test_sanitizer.py
priority: high
type: bug
ordinal: 9870
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
scopeAndSanitizeCSS (ownmail/sanitizer/worker.js) returns any selector that contains the substring `#ownmail-email-content` unchanged, treating it as already scoped. Sender CSS can name the reader container inside a negation or relational pseudo-class and still match application elements outside it. The worker keeps both rules below verbatim:

```css
.ownmail-reader-actions:not(#ownmail-email-content) { display: none !important; }
body:has(#ownmail-email-content) .ownmail-reader-actions { display: none !important; }
```

view_email embeds sanitized styles in the application document (_extract_body_content, templates/email.html), so either rule hides the trusted reader toolbar. The established effect is restyling application UI; no script execution has been shown.

Scope every sender selector whatever it names, keeping the selectors scopeQualifiedBodySelector generates and the existing html/body mapping. Sender CSS has no legitimate need to reference the reader container. test_qualified_body_selectors_keep_author_scoped_rules_unchanged asserts the current pass-through of author-scoped rules; that expectation is the defect and must change with the fix.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 After scoping, every sender selector, including selectors inside @media, @supports, @layer, @container and nested rules, can match only descendants of #ownmail-email-content, whether or not it names the reader container.
- [x] #2 Selectors that do not name the reader container keep their current output, including scopeQualifiedBodySelector results and the html/body mapping.
- [x] #3 test_sanitizer regressions with synthetic CSS place the reserved ID inside :not(), :is(), :where() and :has(), after a sibling combinator, and in one selector of a list; each fails against the current substring shortcut. The author-scoped test expectation is revised with a stated reason.
- [x] #4 A browser regression renders real worker output beside a trusted .ownmail-reader-actions element under the reader CSP and asserts the toolbar stays displayed.
- [x] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Isolation alternative for this task, TASK-133 and TASK-134, judged from the current code. All three exist because message HTML and CSS share the application document.

A sandboxed srcdoc iframe without allow-scripts or allow-same-origin gives the message an opaque origin. Message CSS could not select application elements, application scripts could not find message elements by ID, and a corrupted client rewrite would stay inside the frame. That removes the whole class, and the worker could drop container scoping (selector rewriting in scopeAndSanitizeCSS, scopeQualifiedBodySelector) and _extract_body_content's body-attribute transfer. srcdoc documents inherit the parent's CSP, so remote-content blocking should carry over; that needs a test.

The cost is in the parent-side reader code. An opaque-origin frame cannot be read by the parent, but four features operate on the message DOM from the parent today: email-fit.js measures scrollWidth and sets zoom, email-contrast.js reads computed styles and wraps nodes to repair contrast, applyEmailTheme edits style elements, and the frame height must follow content height. Without allow-scripts none of these can run inside the frame either, so each would move into the worker or be dropped. Links would need allow-popups and allow-popups-to-escape-sandbox; forms would stay blocked. A middle option, allow-same-origin without allow-scripts, keeps parent DOM access and still separates CSS and ID namespaces, at the cost of moving those scripts onto the frame document and sizing the frame.

Recommendation: land point fixes in this task, TASK-133 and TASK-134 now; each is local and testable. Record the iframe as the structural follow-up, because these defects follow several earlier fixes to message CSS and markup handling (TASK-56, TASK-119, TASK-120, TASK-124), and isolation would retire scoping code rather than extend it. Filing it is a maintainer decision.

Not tested: @font-face, @keyframes and other global at-rules are left unscoped by design and apply to the whole document under point fixes.

Implemented as point fixes; iframe isolation is re-evaluated separately.

Root cause: the scoper trusted text rather than structure. Any selector containing #ownmail-email-content passed through as already scoped. postcss's comma split ignores comments, so `.a/*(*/, .x` left `.x` unscoped. The html/body mapping turned `body ~ .x` into `#ownmail-email-content ~ .x`. @scope roots were never scoped, although declarations directly inside @scope style the root. Separately, postcss and browsers tokenize differently: postcss continues a string past a newline and does not treat `URL(`, `url( x)`, `.url(` or escaped `u\rl(` as url tokens, so a rule postcss read as string or comment text reached the page unscoped. Each case hid a trusted element in Chromium.

Fix in ownmail/sanitizer/worker.js:
- Every selector is prefixed, whatever it names. The html/body mapping and scopeQualifiedBodySelector output are unchanged except where the result would select a sibling of the container: `body + x` and `html ~ x` fall back to the plain prefix, and a selector starting with + or ~ (invalid in a top-level rule) drops its rule.
- Selector lists split at the commas a browser sees. A small tokenizer follows CSS Syntax 3 for structure only: comments, strings ended by newlines, url tokens, escapes and blocks.
- @scope roots are scoped like selectors; a missing root becomes (#ownmail-email-content).
- The scoped output is re-read with the same tokenizer. If any style rule or @scope root a browser would find is not confined to the container, the stylesheet becomes `/* CSS parse error */`. Only malformed CSS reaches this. Synthetic stylesheets in the shapes Word, Outlook, newsletter and utility-class generators emit give byte-identical output before and after; a 1.4 MiB stylesheet takes about 11% longer.
- Nested rules (&, relative selectors) and rules inside @scope keep the existing prefix. They stay confined and keep the existing loss of nesting semantics.

AC #2: selectors that name neither the container nor a sibling relation keep their output. The changed outputs listed above all selected application elements, so AC #1 takes precedence there.

Evidence: new test_sanitizer cases put the reserved ID inside :not(), :is(), :where() and :has(), around sibling combinators and in one selector of a list, each in top-level, @media, @supports, @layer, @container and nested contexts. Further cases cover sibling mappings, comment-hidden commas, @scope roots and stylesheets that postcss and browsers read differently. test_reader_body_style renders real worker output beside the reader toolbar under the reader CSP. All new cases and the two revised expectations fail against the previous worker. A random differential check of 9000 stylesheets built from parser-confusing fragments found no rule styling elements outside the container in Chromium; the previous worker leaked in 151 of 3000.

Follow-up, not fixed here. These act through global names or the page box, not selectors. Confirmed in Chromium with a synthetic page unless noted:
- @property: registering an application custom property such as --ownmail-text with inherits: false recolors application UI. Small fix: drop sender @property rules.
- @keyframes: a sender `@keyframes ownmail-spin` replaces the loading spinner animation. Fix: drop or rename sender keyframes in the ownmail- namespace, comparing unescaped names.
- @font-face: a family named like the first available UI font (-apple-system on macOS; Segoe UI or Roboto elsewhere, unverified) replaces the application font, which allows glyph substitution in trusted text such as the sender line. Not small: needs a generic-only UI font stack or renaming sender families and every reference to them.
- @page (by inspection, not rendered): PDF export prints with preferCSSPageSize, and sender @page rules follow the template's, so they can change page size and margins and add margin-box text. Word-generated messages commonly carry @page WordSection1, so dropping @page changes their PDFs and needs a decision.
- @counter-style, @position-try, @font-palette-values, @view-transition, @layer and @namespace have no current effect on reader UI.
- Related (by inspection): #ownmail-email-viewport has no containment, so scoped position: fixed content can still cover application UI.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Every sender selector and @scope root is confined to the reader container, whatever it names. Selector lists split where browsers split, sibling mappings fall back to the plain prefix, and a stylesheet that postcss and browsers read differently is discarded after a browser-faithful re-read. New sanitizer and browser regressions fail on the previous worker and pass now. With browser tests required, 4465 tests pass at 96.61% coverage and the full pre-push gate passes. Global at-rule follow-ups (@property, @keyframes, @font-face, @page) and fixed-position overlays are recorded in the notes.
<!-- SECTION:FINAL_SUMMARY:END -->
