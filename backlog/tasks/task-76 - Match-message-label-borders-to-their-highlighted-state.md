---
id: TASK-76
title: Match message label borders to their highlighted state
status: In Progress
assignee: []
created_date: '2026-09-14 03:16'
updated_date: '2026-09-14 03:19'
labels: []
dependencies: []
priority: low
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Message labels keep a gray border when their background is highlighted. Use the shared accent border for hover and keyboard focus.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Hovered and keyboard-focused message labels use the accent border in light and dark themes, with the keyboard focus indicator preserved.
- [x] #2 Verify browser rendering and pass the full pre-push checks.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Labels now use the selected background and shared accent border on hover and keyboard focus. Chromium checks on the rendered message template passed in both themes: border color, unchanged dimensions, restored neutral styling, and preserved keyboard focus outline. Inspected light and dark screenshots. Full pre-push checks passed using the project virtual environment.
<!-- SECTION:NOTES:END -->
