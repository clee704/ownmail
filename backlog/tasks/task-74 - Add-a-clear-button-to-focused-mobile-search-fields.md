---
id: TASK-74
title: Add a clear button to focused mobile search fields
status: Done
assignee: []
created_date: '2026-09-13 20:45'
updated_date: '2026-09-13 21:00'
labels: []
dependencies: []
priority: low
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Show an X control inside nonempty focused search fields on mobile. Clear the query without submitting and keep the input focused.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Mobile search fields show an accessible clear button only while the field contains text and has focus.
- [x] #2 Clearing preserves input focus, does not submit, and updates query-dependent sort options.
- [x] #3 Verify phone and desktop behavior in both themes and pass the full pre-push checks.
- [x] #4 When the mobile clear button is hidden, search text uses the normal right inset, including after focus and blur.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added a shared search-field partial with an accessible mobile clear button. Clearing emits an input event, keeps focus, and does not submit. All 40 Chromium and WebKit checks passed across phone and desktop widths in both themes, including touch and keyboard clearing, empty and blur visibility, responsive resizing, and relevance-sort reset. WebKit touch testing caught click suppression from canceling pointerdown; canceling mousedown preserves focus and click delivery. Inspected phone previews in both themes. Focused regressions fail without the control and pass with the implementation. Full pre-push checks passed with 2,429 tests passing, one expected failure, and 95.55% coverage.

Reopened after a report of clipped text while the field was unfocused. The initial checks covered button visibility but missed the permanent right padding reserved for the hidden button.

Restricted the extra right padding to the same focused, nonempty state that shows the clear button. Chromium and WebKit reproduced the clipping before the fix and confirmed that long queries regain the normal text width initially and after blur. All 32 before/after checks passed across phone and desktop breakpoint widths in both themes, including empty fields. Inspected the before/after phone screenshots. Full pre-push checks passed.
<!-- SECTION:NOTES:END -->
