---
id: TASK-82
title: Use consistent focus borders for settings fields
status: Done
assignee: []
created_date: '2026-09-14 07:16'
updated_date: '2026-09-14 07:23'
labels: []
dependencies: []
priority: low
ordinal: 86000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Apply the search-field focus border treatment to settings text fields, number fields, textareas, and selects.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings fields use the accent color on their existing border while focused, without an outer outline or size change, in both themes.
- [x] #2 Search fields keep their focus styling, and buttons, checkboxes, and radio buttons retain their keyboard focus indicators.
- [x] #3 Verify phone and desktop layouts in Chromium and WebKit, and pass the full pre-push checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added a focus rule for the existing settings control selector, covering text and number inputs, both selects, and the textarea. Chromium reproduced the offset outline before the change. Chromium and WebKit each passed 28 field checks across light and dark themes at phone and desktop widths: accent borders while focused, no outer outline, unchanged dimensions, and border reset after blur. Search styling and keyboard indicators on other controls also passed. Inspected browser previews in both themes. Full pre-push checks passed with browser tests required. Implementation committed in fed67a3.
<!-- SECTION:NOTES:END -->
