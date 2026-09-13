---
id: TASK-46
title: Refine sender navigation and reader hierarchy
status: In Progress
assignee: []
created_date: '2026-09-13 03:48'
updated_date: '2026-09-13 04:00'
labels: []
dependencies: []
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Address the remaining compact UI feedback: align the shell divider, make sender links find messages by name or address, reorganize reader actions, and reveal metadata from the timestamp.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The header and sidebar divider align at desktop widths.
- [ ] #2 Sender links in lists and the reader return matching display names or addresses.
- [x] #3 Reader actions sit above a subject aligned with the message body, with Back separated from other actions.
- [x] #4 Mobile readers replace the search row with message actions and retain compact spacing.
- [x] #5 The timestamp reveals message metadata without a separate Message details row.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Verified matching header/sidebar borders in expanded and collapsed desktop navigation. Subject and body share their left edge. Readers below the navigation breakpoint replace search with Back and More; the global menu remains above reader controls. Timestamp toggles full metadata by mouse and keyboard. Checked synthetic pages at 320, 390, 768, 1440, and 1441 px in light and dark themes. The expanded action set and sender matching remain pending user choices; sender prototypes are preserved in ignored build/ui-review patches. Recommended sender behavior is exact address with name fallback, since AND excludes renamed senders and OR includes different people with the same name. No sender query behavior changed in this checkpoint.
<!-- SECTION:NOTES:END -->
