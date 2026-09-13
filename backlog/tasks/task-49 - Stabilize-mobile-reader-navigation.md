---
id: TASK-49
title: Stabilize mobile reader navigation
status: In Progress
assignee: []
created_date: '2026-09-13 04:43'
updated_date: '2026-09-13 04:48'
labels: []
dependencies: []
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Stabilize the mobile reader toolbar while returning to results. Hide the approved mobile branding row and keep Back, Trash, and More in one top row.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Returning to results keeps the mobile reader toolbar stable until navigation.
- [x] #2 Back preserves the result URL, list scroll position, and focus.
- [x] #3 The agreed mobile reader header layout keeps message actions and metadata accessible, without changing the desktop layout.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The user confirmed hiding the mobile branding row. The reported jump occurs in Safari launched from the iPhone Home Screen. Moved the toolbar outside the message article and replaced fixed positioning with a sticky row in normal document flow. Back now shows loading feedback immediately while preserving the result URL, scroll position, and focus. Modified and prevented clicks keep native behavior. Resizing from desktop navigation moves focus to the visible Back link. Browser checks at 320, 390, and 1440 pixels verified sticky positioning during scroll, list restoration, metadata and More access, no horizontal overflow, and unchanged desktop subject/body alignment. The specific iPhone Home Screen transition was not reproduced in the available browser and still needs device confirmation. Focused regression tests and the full pre-push checks pass; removing Back loading feedback fails the mutation check.
<!-- SECTION:NOTES:END -->
