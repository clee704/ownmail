---
id: TASK-54
title: Restore conditional message body spacing
status: Done
assignee: []
created_date: '2026-09-13 06:20'
updated_date: '2026-09-13 06:24'
labels:
  - ui
  - bug
dependencies: []
priority: high
ordinal: 57000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The UI redesign sets horizontal padding to zero for message bodies that the sanitizer identifies as needing reader-provided spacing. Simple HTML notifications then touch the edge of the light message canvas. Restore the distinction between plain text, HTML needing padding, and HTML with an authored layout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Simple HTML has readable horizontal padding on phone and desktop layouts in both themes.
- [x] #2 Plain text retains readable spacing and HTML with its own layout does not gain a second frame.
- [x] #3 Regression checks fail with the zero-padding rules, and the full pre-push gate passes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Confirmed regression in a7d6062: the redesign removed horizontal padding from the conditional body classes; 7694b9f retained zero horizontal padding on phones. Restore the padded HTML inset to 16px above 600px and 8px on phones. Plain text stays aligned with metadata because the redesign already removed the old negative content-area margin. Authored layouts retain their existing spacing. Synthetic message routes use the real sanitizer. Chromium and WebKit checks cover simple HTML, plain text, styled HTML and a wide newsletter at 390px, 768px and 1440px in both themes. Before the fix, all 12 simple-HTML inset checks failed; the other 36 cases passed. After the fix all 48 cases pass, including page overflow and wide-message fitting.

Visual inspection confirms the inset on a phone-sized dark reader. Independent review found no actionable issue. The full pre-push gate passed, including formatting, lint, dependency checks and the complete test suite with its coverage gate.

Implementation committed in acfea3a.
<!-- SECTION:NOTES:END -->
