---
id: TASK-134
title: Switch message dark-mode rules without rewriting CSS text
status: To Do
assignee: []
created_date: '2026-10-10 05:32'
labels:
  - security
dependencies: []
references:
  - ownmail/static/email-reader.js
  - ownmail/sanitizer/worker.js
  - tests/test_email_contrast.py
priority: medium
type: bug
ordinal: 9900
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
applyEmailTheme (ownmail/static/email-reader.js) rewrites the text of each message style element with a regular expression that ignores CSS strings, comments and nesting. In the light theme it deletes `@media (prefers-color-scheme: dark)` blocks; in the dark theme it unwraps them. It runs when the content area has `data-supports-dark="true"`, which detectSupportsDarkMode (ownmail/sanitizer/worker.js) sets whenever `prefers-color-scheme: dark` appears in a style element's text, including inside a CSS string.

Sender CSS can put that text and a toolbar-hiding rule inside custom-property strings. The worker scopes the rule and the strings stay inert. The light-theme rewrite then deletes a span that starts in one string and ends in another, and the rest parses as an unscoped top-level rule:

```text
worker output: #ownmail-email-content .a{--x:'@media (prefers-color-scheme:dark){';--y:"}';}.ownmail-reader-actions{display:none!important}"}
after rewrite: #ownmail-email-content .a{--x:'';}.ownmail-reader-actions{display:none!important}"}
```

Chromium parses `.ownmail-reader-actions { display: none !important; }` from the rewritten text and computes the toolbar's display as none. Strict CSS parsers reject the text, so the escape relies on browser error recovery. No script execution has been shown.

Stop rewriting message CSS as text. Either toggle parsed rules through the CSSOM, for example by changing the media text of matching CSSMediaRule objects, or have the worker rewrite dark-mode at-rules from its AST so the client only toggles a class. Detect dark-mode support from parsed at-rule conditions rather than substrings.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 No client code rewrites message style text; switching the app theme changes only parsed rules or classes, and sender rules stay scoped in both themes and after repeated switches.
- [ ] #2 detectSupportsDarkMode reports support only for a parsed @media condition containing prefers-color-scheme: dark, not for matching text inside strings or comments.
- [ ] #3 Legitimate dark-mode rules still follow the app theme in both directions, and existing contrast and theme tests pass.
- [ ] #4 A browser regression with the synthetic string payload above, using the real worker and email-reader.js, asserts the toolbar stays displayed in both themes; it fails against the current regular expressions.
- [ ] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The current dark-theme unwrap also discards any other condition in the same media query, such as a width limit. A CSSOM or AST approach can keep those conditions.

A sandboxed message iframe would confine any rewrite error to the message document; see the isolation notes in TASK-131. The point fix is recommended for now.
<!-- SECTION:NOTES:END -->
