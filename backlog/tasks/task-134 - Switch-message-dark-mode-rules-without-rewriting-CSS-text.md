---
id: TASK-134
title: Switch message dark-mode rules without rewriting CSS text
status: Done
assignee: []
created_date: '2026-10-10 05:32'
updated_date: '2026-10-10 05:59'
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
- [x] #1 No client code rewrites message style text; switching the app theme changes only parsed rules or classes, and sender rules stay scoped in both themes and after repeated switches.
- [x] #2 detectSupportsDarkMode reports support only for a parsed @media condition containing prefers-color-scheme: dark, not for matching text inside strings or comments.
- [x] #3 Legitimate dark-mode rules still follow the app theme in both directions, and existing contrast and theme tests pass.
- [x] #4 A browser regression with the synthetic string payload above, using the real worker and email-reader.js, asserts the toolbar stays displayed in both themes; it fails against the current regular expressions.
- [x] #5 The full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The current dark-theme unwrap also discards any other condition in the same media query, such as a width limit. A CSSOM or AST approach can keep those conditions.

A sandboxed message iframe would confine any rewrite error to the message document; see the isolation notes in TASK-131. The point fix is recommended for now.

Chose the CSSOM approach. applyEmailTheme now walks each message style element's parsed sheet, including nested grouping rules, and sets the media text of CSSMediaRule objects. Each (prefers-color-scheme: dark) feature becomes the constant (width >= 0px) in the dark theme and (width < 0px) in the light theme, starting from the rule's original media text. Setting media text parses only a media query list, so sender text cannot become a new rule, and other conditions such as width limits or not/or logic keep working. The style text is never written. A worker-side variant would have changed rule specificity or required duplicating rules, and would have overlapped the concurrent scoper changes. Dark rules now follow the reader canvas class (app dark and data-supports-dark) for every message, so a dark rule the worker's parser misses stays off on a forced light canvas instead of following the OS.

detectSupportsDarkMode parses each style with PostCSS (map: false), walks @media at-rules, drops string and comment tokens from the condition, and only then looks for the prefers-color-scheme: dark feature. A comment between the feature name and value now counts, as browsers accept it.

Tests: tests/test_reader_body_style.py renders a synthetic message through the real worker and email-reader.js in a browser with the OS set to dark, switches the app theme twice in each direction, and checks that the toolbar stays displayed, that plain, width-limited and @supports-nested dark rules follow the app theme, and that the style text is unchanged. Against the original code the toolbar computes to display: none in the light theme. tests/test_sanitizer.py covers parsed conditions and string, comment and light-only text for detection; five of its cases fail against the original regular expression. The new browser test and existing theme tests also pass in WebKit.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Message dark-mode rules now switch with the app theme by changing the media condition of parsed CSSMediaRule objects, never by rewriting style text, and the worker detects dark-mode support only from parsed @media conditions. Browser and worker regressions cover the string payload that previously hid the reader toolbar.
<!-- SECTION:FINAL_SUMMARY:END -->
