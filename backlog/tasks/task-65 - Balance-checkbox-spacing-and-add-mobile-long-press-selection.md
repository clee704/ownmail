---
id: TASK-65
title: Balance checkbox spacing and add mobile long-press selection
status: Done
assignee: []
created_date: '2026-09-13 08:17'
updated_date: '2026-09-13 08:24'
labels:
  - ui
  - mobile
dependencies: []
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Center list checkboxes between the edge and message text. On phone layouts, hide row checkboxes until a message is held or selected with the header control; retain normal taps and scrolling.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Visible checkboxes have equal horizontal gaps to the list edge and message text, with header and row checkboxes aligned.
- [x] #2 Phone list checkboxes are hidden initially, revealed by long press or header selection, and hidden again when selection is cleared.
- [x] #3 Search and Trash preserve normal taps, scrolling, desktop selection, and disabled action controls, with regression coverage.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Visible checkboxes use a centered 44px column with equal 15px gaps to the list edge and message text. Phone rows reclaim the checkbox column while unselected. Verified 256 Chromium and WebKit layout cases across four widths, both pointer types, both themes, Search and Trash, and empty, full, partial, and cleared selection states; header visibility, checkbox alignment, touch target size, gutters, and horizontal overflow pass.

Shared selection logic now serves Search and Trash. A 500ms mobile hold selects the message and suppresses release navigation; movement beyond 10px, cancellation, scrolling, multitouch, blur, and breakpoint changes cancel pending holds. Native Chromium touch checks verify sender/subject holds, scroll cancellation, and ordinary sender taps; WebKit dispatched-touch checks verify holds and clear selection. All 56 UI shell tests pass.

The 76 combined UI shell and message-action tests pass. Deliberately removing hold selection or timer cancellation makes the focused tests fail. Full pre-push hooks pass. Independent review identified a 2px sender/subject overlap in the desktop fallback without subgrid; its placeholder now includes the grid gap within the sender column.

The fallback correction restores a 6px sender/subject gap at desktop width with subgrid disabled. Final review and all pre-push hooks pass.
<!-- SECTION:NOTES:END -->
