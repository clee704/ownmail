---
id: TASK-61
title: Align search controls and refine list header spacing
status: Done
assignee: []
created_date: '2026-09-13 07:39'
updated_date: '2026-09-13 07:55'
labels:
  - ui
  - mobile
dependencies: []
type: bug
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Match search input and button heights, reduce the gap below mobile search, balance list toolbar spacing, and keep the toolbar divider visible when messages are selected.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Search input and submit button have matching heights on mobile and desktop.
- [x] #2 Mobile search has slightly less bottom spacing and the fixed header reserves the matching height.
- [x] #3 List toolbar controls have equal top and bottom spacing without an extra top margin.
- [x] #4 The divider between the toolbar and messages stays visible in selected and unselected states in both themes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Search controls share explicit 32px desktop and 44px phone heights with native appearance disabled. Phone search bottom padding is 12px instead of 16px; the 105px header contains its rows and border. Removed the extra 8px toolbar top margin and its unused class. Selected toolbars use the existing stronger theme border in Search and Trash. Verified 120 synthetic-data layout cases in Chromium and WebKit at 320, 390, 430, 768, and 1280px across both themes and none, partial, and full selection. Checks cover control alignment, balanced spacing, header and drawer offsets, list boundaries, clear selection, and overflow. Inspected phone screenshots in both themes. Independent review found no actionable issues. Physical iPhone rendering was not checked. Full pre-push hooks passed, including lint, dependency checks, and the full test suite with its coverage gate.

Reopened after a phone screenshot showed a remaining visible height mismatch. Recheck painted edges as well as CSS dimensions.

Follow-up: moved the search field border and background to its label wrapper, sharing the button height. The inner input is transparent and borderless, with native margins and shadows reset. Both phone controls use 16px text; focus remains visible on the field wrapper. Passed 60 synthetic browser cases in Chromium and WebKit across 320, 390, 600, 768, and 1280px, both themes, populated and empty Search, and the shared Help header. Checked outer bounds, overflow, focus, and keyboard submission; inspected phone screenshots. The original stylesheet also had equal measured outer bounds. The supplied JPEG does not establish a geometric defect, so physical iPhone appearance remains unverified. Independent review found no actionable issues. Full pre-push checks passed.
<!-- SECTION:NOTES:END -->
