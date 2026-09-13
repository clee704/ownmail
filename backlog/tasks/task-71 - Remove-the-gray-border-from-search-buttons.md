---
id: TASK-71
title: Remove the gray border from search buttons
status: Done
assignee: []
created_date: '2026-09-13 20:19'
updated_date: '2026-09-13 20:25'
labels: []
dependencies: []
priority: low
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Use the shared primary-button border styling so the yellow search button has a consistent edge in both themes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Search buttons have no gray border in light and dark themes, including hover, while retaining their dimensions and keyboard focus outline.
- [x] #2 The full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed the search-only border override, retaining the shared transparent border. Chromium verified light and dark themes, hover, keyboard focus, and unchanged dimensions. All pre-push hooks passed in an isolated copy containing only this change.
<!-- SECTION:NOTES:END -->
