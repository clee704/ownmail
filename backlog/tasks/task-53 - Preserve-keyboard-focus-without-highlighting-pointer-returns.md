---
id: TASK-53
title: Preserve keyboard focus without highlighting pointer returns
status: In Progress
assignee: []
created_date: '2026-09-13 05:29'
updated_date: '2026-09-13 05:42'
labels:
  - web
  - ux
dependencies: []
priority: medium
type: bug
ordinal: 56000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Returning to results with the reader Back button forces focus onto the previous message row, showing a blue focus border after touch or mouse activation. Restore row focus only for keyboard or equivalent non-pointer activation while retaining the saved scroll position.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Touch and mouse activation of the reader Back button restores the saved list position without forcing focus onto the message row.
- [x] #2 Keyboard or equivalent non-pointer Back activation restores focus to the previous message row without moving the saved scroll position.
- [x] #3 Focused regressions preserve modified-click and native-history behavior and fail when return focus is always applied or always omitted.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Back records whether activation is keyboard-style (click detail zero). The returned list restores row focus only for that activation; saved scroll restoration remains unconditional. Verified touch return in the iPhone Home Screen simulator has no row outline, and keyboard Enter on Back restores the 2px focus-visible indicator. All 37 reader tests and the full pre-push gate pass. Pointer cases fail the previous implementation, and always-focus and never-focus mutations are both rejected. The separate native-history jump is handled in TASK-51.
<!-- SECTION:NOTES:END -->
