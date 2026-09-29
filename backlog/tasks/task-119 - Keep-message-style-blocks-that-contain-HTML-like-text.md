---
id: TASK-119
title: Keep message style blocks that contain HTML-like text
status: To Do
assignee: []
created_date: '2026-09-29 06:39'
labels:
  - ui
dependencies: []
priority: medium
type: bug
ordinal: 19500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The sanitizer worker drops a message's whole style block in two cases. When the block wraps its rules in HTML comment markers (<!-- ... -->), a legacy convention some mail generators still emit, PostCSS fails to parse the closing --> and the worker replaces the stylesheet with /* CSS parse error */. Chromium applies the same rules. When the CSS text contains < followed by a letter, / or ! that PostCSS does not escape, as in a comment such as /* reset <p> margins */ or a content string, DOMPurify's markup probe removes the style element. Both cases reproduce with synthetic messages on DOMPurify 3.3.1 with PostCSS 8.5.6 and on DOMPurify 3.4.16 with PostCSS 8.5.28. PostCSS 8.5.28 escapes only <style, </style and <!-- as \3c in its output, so those sequences no longer trigger the probe. Keep the authored rules in both cases without letting style text close the style element.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A synthetic message whose style rules are wrapped in <!-- --> keeps its scoped rules after sanitization
- [ ] #2 A synthetic message whose CSS comments or strings contain markup-like text keeps its scoped rules, and no style text can close the style element
- [ ] #3 The full pre-push gate passes
<!-- AC:END -->
