---
id: TASK-60
title: Simplify mobile mail controls and feedback
status: In Progress
assignee: []
created_date: '2026-09-13 07:26'
updated_date: '2026-09-13 07:34'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Refine the mobile list and reader controls based on UI feedback: add breathing room below search, remove the list heading and place sorting in a menu, simplify selection, move reader trash into its menu, restyle the external-image banner, and dismiss successful feedback automatically.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Search has more space above the list toolbar; the visible list heading is removed and sorting remains available in a kebab menu.
- [x] #2 Selecting messages uses a compact toolbar without increasing its height, with clear count, cancel, and bulk actions.
- [x] #3 Reader trash and restore actions are available through the message menu.
- [x] #4 The external-image banner uses coordinated neutral and accent colors in light and dark themes.
- [x] #5 Successful sender feedback disappears automatically without hiding newer feedback or pending and error states.
- [x] #6 Mobile and desktop layouts and relevant interactions are verified, and repository checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed the visible list heading and placed sorting in a native radio group in the kebab menu. Search has 12px more bottom padding on phones. Selection replaces refresh and pagination with the count and icon actions, keeping the toolbar height stable; clearing selection restores focus. Long ranges truncate when necessary to keep 44px phone controls inside the viewport. Reader trash and restore are in the message menu. The image banner uses neutral surfaces and accent actions. Success notices dismiss after four seconds; pending and errors remain visible, and new feedback cancels old timers.

Removed the redundant All Mail sort override so an explicit oldest-first choice is honored. The existing route regression reproduced the failure before the fix and now covers both date orders with empty and text queries, menu state, and pagination.

Verified synthetic-data layouts in Chromium at 320, 390, 430, and 1280px in light and dark themes, including selection, menus, reader banner, toast expiry, and long pagination ranges. WebKit at 390px also passed selection height, menu bounds, and overflow checks. New interaction tests were checked with deliberate regressions. Independent review found no must-fix issues. Full pre-push hooks pass, including lint, dependency checks, and the full test suite with the 95% coverage gate.
<!-- SECTION:NOTES:END -->
