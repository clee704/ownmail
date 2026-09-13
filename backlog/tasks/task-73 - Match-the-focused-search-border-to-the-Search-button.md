---
id: TASK-73
title: Match the focused search border to the Search button
status: Done
assignee: []
created_date: '2026-09-13 20:36'
updated_date: '2026-09-13 20:39'
labels: []
dependencies: []
priority: low
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Replace the offset search-field focus outline with an accent-colored existing border.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Focused search fields use the Search button accent color on their existing border, with no outer outline or size change, in both themes.
- [x] #2 Show a browser preview and pass the full pre-push checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Changed the focused search field border to the shared accent color and removed the offset outline. Chromium and WebKit checks passed for Search and Help at phone and desktop widths in both themes, covering focus color, border width, unchanged dimensions, blur, and the button focus outline. Inspected the phone previews with synthetic messages. Full pre-push checks passed.
<!-- SECTION:NOTES:END -->
