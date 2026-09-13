---
id: TASK-62
title: Align select-all and message checkboxes
status: Done
assignee: []
created_date: '2026-09-13 07:45'
updated_date: '2026-09-13 07:47'
labels:
  - ui
  - mobile
dependencies: []
type: bug
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Align the select-all checkbox with the message checkbox column in Search and Trash across phone, tablet, and desktop layouts.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Select-all and message checkboxes have the same horizontal center with fine and coarse pointers, including selected states.
- [x] #2 Phone checkbox targets remain at least 44px wide and tall, and list controls remain usable without horizontal overflow.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Toolbar and message rows share a 36px checkbox column on larger screens and a 44px column on phones, with matching cell padding. Removed the separate coarse-pointer width. The touch-phone message checkbox stays in place; its wider target moves the text 4px right. Verified 192 Chromium and WebKit layout cases across four widths, both pointer types, both themes, Search and Trash, and all selection states. Checkbox alignment, 44px phone targets, spacing, selection controls, and overflow checks pass. Independent review found no issues. Full pre-push hooks passed.
<!-- SECTION:NOTES:END -->
