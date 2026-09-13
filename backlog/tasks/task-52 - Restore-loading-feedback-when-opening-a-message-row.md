---
id: TASK-52
title: Restore loading feedback when opening a message row
status: In Progress
assignee: []
created_date: '2026-09-13 05:15'
updated_date: '2026-09-13 21:29'
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

Show a small spinner in the clicked row after the existing 200 ms delay. Use the Search button accent color, gently mute the sender and subject, and keep the date column width stable. Keep navigation available while a message is opening. Track the latest same-tab destination so repeated clicks, another message, or Settings cannot leave stale row feedback.

Keep normal browser navigation and separate sender and checkbox interactions. Remove the obsolete listener. This task does not change page transitions, history, or offline recovery.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A normal message-row click navigates immediately; after 200 ms, a slow response shows a 14 px spinner using --ownmail-accent, with no visible loading label or layout shift. Pending sender and subject use --ownmail-secondary in both themes.
- [x] #2 Fast navigation and modified or prevented clicks do not start row feedback. Sender links, checkboxes, and mobile long-press selection retain their separate behavior; controls remain usable while navigation is pending.
- [x] #3 Repeated clicks on the same pending message keep one indicator without restarting its visual delay. A new message moves pending feedback; another same-tab destination clears it. Superseded timers cannot restore stale feedback.
- [x] #4 Returning through browser history clears pending styling. Cancelling navigation must leave the message link usable for retry. Reduced motion disables spinner animation, and a polite hidden status announces loading.
- [x] #5 Regression coverage exercises rendered message links and fails with the obsolete selector. Slow navigation checks cover repeated clicks, message-to-message navigation, and message-to-Settings navigation; the unused listener is removed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented the approved row feedback: a 14 px spinner with a 2 px stroke using the Search button accent, muted sender/subject text, and a polite hidden loading status. The date content retains its space while hidden, so the row and date column do not move. Reduced motion disables spinner animation.

Native links remain usable. Repeated message clicks keep the current feedback delay and spinner; choosing another message or destination removes stale row feedback. Checkboxes, search editing, modified clicks, and mobile long-press selection keep their separate behavior. Escape calls the browser Stop operation before clearing a pending message; Escape consumed by the mobile navigation panel only closes that panel. Page lifecycle events clear feedback for history navigation and retry.

Validation: 11 Chromium tests pass against held native document requests, including message replacement, Settings, fast responses, cancellation/retry, and light/dark desktop/mobile layout. Focused tests cover the exact 200 ms delay, modifiers, mobile selection, and Escape handling. Both rendered-list regression cases fail with the obsolete selector substituted in memory. Independent review found no actionable issues. The full pre-push gate remains to be run before closing the task.
<!-- SECTION:NOTES:END -->
