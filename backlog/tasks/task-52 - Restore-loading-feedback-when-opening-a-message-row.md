---
id: TASK-52
title: Restore loading feedback when opening a message row
status: To Do
assignee: []
created_date: '2026-09-13 05:15'
updated_date: '2026-09-13 21:07'
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
- [ ] #1 A normal message-row click navigates immediately; after 200 ms, a slow response shows a 14 px spinner using --ownmail-accent, with no visible loading label or layout shift. Pending sender and subject use --ownmail-secondary in both themes.
- [ ] #2 Fast navigation and modified or prevented clicks do not start row feedback. Sender links, checkboxes, and mobile long-press selection retain their separate behavior; controls remain usable while navigation is pending.
- [ ] #3 Repeated clicks on the same pending message keep one indicator without restarting its visual delay. A new message moves pending feedback; another same-tab destination clears it. Superseded timers cannot restore stale feedback.
- [ ] #4 Returning through browser history clears pending styling. Cancelling navigation must leave the message link usable for retry. Reduced motion disables spinner animation, and a polite hidden status announces loading.
- [ ] #5 Regression coverage exercises rendered message links and fails with the obsolete selector. Slow navigation checks cover repeated clicks, message-to-message navigation, and message-to-Settings navigation; the unused listener is removed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Design reviewed in an interactive preview. The spinner uses the Search button fill (#edb928), with a 2 px stroke. Pending text uses the existing secondary color; the spinner stays at full strength. Use the neutral hover background for the pending row so it remains distinct from checkbox selection.

The browser owns replacement of pending native navigation. Keep feedback state separate from request state: clicking another destination must remove the old row indicator. Repeated clicks must not stack indicators or restart the visual delay. Avoid disabling the row, which could prevent retry after cancellation.

Checkbox changes and typing do not cancel an already pending native navigation. The destination may still open afterward. Modified clicks must leave the current pending destination alone. The existing global overlay only guards Ctrl/Meta, so any shared feedback handler must use the complete normal-click predicate.

The preview simulates these interactions; production implementation and slow native-navigation regression coverage remain outstanding. No acceptance criteria have been completed.

Native navigation replacement is defined by the [HTML navigation algorithm](https://html.spec.whatwg.org/multipage/browsing-the-web.html#navigate); this does not imply cancellation of server-side work.
<!-- SECTION:NOTES:END -->
