---
id: TASK-47
title: Limit sender search to the sender name hit area
status: Done
assignee: []
created_date: '2026-09-13 04:31'
updated_date: '2026-09-13 04:33'
labels: []
dependencies: []
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
In message lists, the blank space to the right of a sender should open the message. Keep sender search on the sender name and preserve long-name truncation.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Tapping the sender name opens sender search; blank space beside it opens the message.
- [x] #2 Long sender names remain truncated without overlapping the date or subject.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Limited the sender grid item to its content width, capped at its column width. Browser hit tests at 320, 390 and 1440 px confirm that sender text targets sender search and adjacent whitespace targets the message. Short and ellipsized names retain their layout without overlapping the date or subject. Sender and message navigation also verified. Independent CSS review found no further issues.

Full pre-push checks pass.
<!-- SECTION:NOTES:END -->
