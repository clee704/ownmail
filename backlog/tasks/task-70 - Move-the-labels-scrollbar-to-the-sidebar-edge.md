---
id: TASK-70
title: Move the labels scrollbar to the sidebar edge
status: Done
assignee: []
created_date: '2026-09-13 20:17'
updated_date: '2026-09-13 20:25'
labels: []
dependencies: []
priority: low
ordinal: 74000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Move the navigation scrollbar toward the sidebar right border without changing label text, counts, row widths, or other layout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The labels scrollbar moves to the sidebar right edge while existing navigation content geometry stays unchanged.
- [x] #2 Expanded, collapsed, and mobile navigation retain scrolling and fixed utility links; the full pre-push checks pass.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Moved the scroll container 8px toward the sidebar border with matching negative right margin and positive right padding. All 24 synthetic geometry checks passed in Chromium and WebKit across expanded, collapsed, and mobile navigation, short and overflowing label lists, and automatic and stable scrollbar gutters. Label, count, row, heading, and footer geometry stayed unchanged; scrolling reached the last label. Full pre-push checks passed in an isolated checkout. Implementation committed in 6e75fb0.
<!-- SECTION:NOTES:END -->
