---
id: TASK-46
title: Refine sender navigation and reader hierarchy
status: Done
assignee: []
created_date: '2026-09-13 03:48'
updated_date: '2026-09-13 04:26'
labels: []
dependencies: []
ordinal: 49000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Align the shell and reader, make sender links prefer an exact address with name fallback, keep primary reader controls compact, and reveal metadata from the timestamp.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The header and sidebar divider align at desktop widths.
- [x] #2 Sender links in lists and the reader match the exact email address, falling back to the display name when no address is available.
- [x] #3 Back and Trash or Restore sit above the aligned subject and body; Original and Download stay in More.
- [x] #4 Mobile readers replace the search row with message actions and retain compact spacing.
- [x] #5 The timestamp reveals message metadata without a separate Message details row.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The shell borders and reader text align. Mobile readers reserve the search row for Back, Trash or Restore, and More. More contains Original and Download, conditional image, trust and fitting controls, and Delete forever for trashed messages. Sender links share one URL builder across search, Trash and reader views. Address searches include renamed senders and exclude other people with the same name; name fallback safely quotes punctuation. The existing address parser contract is preserved. Verified desktop and mobile layouts, sender links, checkbox and message navigation, fit controls, and Trash reader controls with synthetic mail. Real database regressions and deliberate mutations cover sender matching and toolbar wiring. Independent review completed; full pre-push checks pass.
<!-- SECTION:NOTES:END -->
