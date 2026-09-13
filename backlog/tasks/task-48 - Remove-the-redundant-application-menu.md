---
id: TASK-48
title: Remove the redundant application menu
status: In Progress
assignee: []
created_date: '2026-09-13 04:36'
updated_date: '2026-09-13 04:40'
labels: []
dependencies: []
ordinal: 51000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Remove the top-right application kebab and its unused layout and script code. Keep the message menu, sidebar navigation, and Settings theme controls working.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The application menu is absent on desktop and mobile, with no empty header column.
- [x] #2 Settings and Search help remain reachable through the sidebar, including mobile keyboard navigation.
- [x] #3 Theme selection in Settings and automatic system-theme updates still work.
- [x] #4 The reader retains its message actions and More menu.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Removed the application menu, its event handlers, obsolete icons, and reserved header column. Settings and Search help remain in the sidebar; theme selection stays in Settings. The reader retains Trash and More. Verified desktop and mobile layouts, mobile navigation, theme persistence, and reader actions in the synthetic preview. Shell tests cover sidebar utilities, saved theme choices, system-theme updates, and reader theme callbacks; three targeted mutations failed as expected. The full pre-push checks pass.
<!-- SECTION:NOTES:END -->
