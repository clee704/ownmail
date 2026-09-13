---
id: TASK-52
title: Restore loading feedback when opening a message row
status: To Do
assignee: []
created_date: '2026-09-13 05:15'
updated_date: '2026-09-13 05:21'
labels:
  - ui
  - ux
dependencies: []
references:
  - ownmail/templates/base.html
  - ownmail/templates/_email_list.html
  - ownmail/templates/_result_state.html
priority: low
type: bug
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Opening a message through its subject or date has no pending feedback on a slow response. base.html attaches showLoading to .ownmail-email-item a, but the shared list renders .ownmail-email-row-link. The result-state template saves the return position on those links without calling showLoading.

Wire the existing delayed loading indicator to message-row navigation and remove the obsolete listener. Keep normal browser navigation, separate sender and checkbox interactions, and the current fast-navigation delay. This task does not change page transitions, history, or offline recovery.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A normal message-row click navigates immediately and shows the existing delayed indicator only when the response is slow.
- [ ] #2 Fast navigation and modified clicks do not flash the overlay; sender links and checkbox interactions retain their existing behavior.
- [ ] #3 A focused regression test exercises the rendered message-row link and fails with the obsolete selector; the unused listener is removed.
<!-- AC:END -->
