---
id: TASK-131
title: Scope message CSS selectors that name the reader container
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
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
- [ ] #1 After scoping, every sender selector, including selectors inside @media, @supports, @layer, @container and nested rules, can match only descendants of #ownmail-email-content, whether or not it names the reader container.
- [ ] #2 Selectors that do not name the reader container keep their current output, including scopeQualifiedBodySelector results and the html/body mapping.
- [ ] #3 test_sanitizer regressions with synthetic CSS place the reserved ID inside :not(), :is(), :where() and :has(), after a sibling combinator, and in one selector of a list; each fails against the current substring shortcut. The author-scoped test expectation is revised with a stated reason.
- [ ] #4 A browser regression renders real worker output beside a trusted .ownmail-reader-actions element under the reader CSP and asserts the toolbar stays displayed.
- [ ] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Isolation alternative for this task, TASK-133 and TASK-134, judged from the current code. All three exist because message HTML and CSS share the application document.

A sandboxed srcdoc iframe without allow-scripts or allow-same-origin gives the message an opaque origin. Message CSS could not select application elements, application scripts could not find message elements by ID, and a corrupted client rewrite would stay inside the frame. That removes the whole class, and the worker could drop container scoping (selector rewriting in scopeAndSanitizeCSS, scopeQualifiedBodySelector) and _extract_body_content's body-attribute transfer. srcdoc documents inherit the parent's CSP, so remote-content blocking should carry over; that needs a test.

The cost is in the parent-side reader code. An opaque-origin frame cannot be read by the parent, but four features operate on the message DOM from the parent today: email-fit.js measures scrollWidth and sets zoom, email-contrast.js reads computed styles and wraps nodes to repair contrast, applyEmailTheme edits style elements, and the frame height must follow content height. Without allow-scripts none of these can run inside the frame either, so each would move into the worker or be dropped. Links would need allow-popups and allow-popups-to-escape-sandbox; forms would stay blocked. A middle option, allow-same-origin without allow-scripts, keeps parent DOM access and still separates CSS and ID namespaces, at the cost of moving those scripts onto the frame document and sizing the frame.

Recommendation: land point fixes in this task, TASK-133 and TASK-134 now; each is local and testable. Record the iframe as the structural follow-up, because these defects follow several earlier fixes to message CSS and markup handling (TASK-56, TASK-119, TASK-120, TASK-124), and isolation would retire scoping code rather than extend it. Filing it is a maintainer decision.

Not tested: @font-face, @keyframes and other global at-rules are left unscoped by design and apply to the whole document under point fixes.
<!-- SECTION:NOTES:END -->
