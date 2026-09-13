---
id: TASK-63
title: Show attachment icons in message lists
status: Done
assignee: []
created_date: '2026-09-13 08:01'
updated_date: '2026-09-13 08:09'
labels:
  - ui
dependencies: []
type: feature
ordinal: 66000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Show a paperclip beside the date for messages with attachments in All Mail, search results, and Trash, using the existing indexed attachment flag.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Only messages with indexed attachments show a paperclip in All Mail, search results, and Trash.
- [x] #2 The indicator has accessible text and remains readable without overlap in narrow and wide layouts in both themes.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Added the existing paperclip SVG beside each message date when the indexed has_attachments flag is set. Browse, full-text search, and Trash queries expose that flag; message links describe it as Has attachments for assistive technology. Database and rendered-page tests cover both flag values, with failing mutation checks. Verified 96 Chromium and WebKit cases across four widths, both themes, and All Mail, search, and Trash, including the fallback without subgrid. Dates align and icons do not overlap sender or subject text. Independent review found no regressions; its pre-existing CLI Trash listing finding is tracked separately in TASK-64.

Committed as da58d83. Full pre-push hooks passed, including the coverage gate.
<!-- SECTION:NOTES:END -->
