---
id: TASK-75
title: Fix clipped attachment icon
status: Done
assignee: []
created_date: '2026-09-13 21:41'
updated_date: '2026-09-13 21:46'
labels:
  - ui
dependencies: []
type: bug
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The paperclip beside message dates is clipped at its right edge. Keep the complete stroke inside the icon viewport in every message list.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The complete paperclip stroke fits inside its SVG viewport.
- [x] #2 Attachment indicators remain aligned beside dates in narrow and wide layouts in both themes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Adjusted the outer arc of the shared paperclip path while preserving its 16-pixel box and 1.6-unit stroke. The full stroke fits within x=1.20–22.86 and y=1.14–21.80 of the 24-unit viewport. Verified the original path exceeds the viewport in WebKit, and inspected before/after mobile screenshots. All 96 Chromium and WebKit layout cases passed across four widths, both themes, All Mail, search, and Trash, with and without subgrid. Existing attachment visibility and accessibility tests passed. Full pre-push hooks passed with browser tests required, including the coverage gate. Fix committed as e4fe341.
<!-- SECTION:NOTES:END -->
