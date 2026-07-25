---
id: TASK-19
title: >-
  Decide which other Gmail pseudo-labels to archive (STARRED, IMPORTANT,
  CATEGORY_*)
status: To Do
assignee: []
created_date: '2026-07-25 06:20'
labels: []
dependencies: []
priority: medium
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-5.3 established that Gmail pseudo-labels recording ephemeral client state should not be archived, and dropped UNREAD on that basis. Gmail's labelIds carry others that _resolve_label_names still passes through into the labels array:

- STARRED - durable user intent, changes only when the user acts. Strongest case for keeping. IMAP's equivalent is \\Flagged, which ownmail does not capture, so keeping it preserves the same Gmail/IMAP asymmetry TASK-5.3 removed for UNREAD.
- IMPORTANT - Gmail's ML guess. Drifts on its own, never refreshed after capture, so it decays exactly like UNREAD did.
- CATEGORY_PERSONAL/SOCIAL/PROMOTIONS/UPDATES/FORUMS - Gmail's tab classification. Topical and stable, so arguably real archive content, but Gmail-only vocabulary with no IMAP counterpart.
- CHAT - marks Hangouts/Chat messages, closer to a message type than a label.

Needs a per-label decision, not a blanket one. If any are dropped, reuse the roles.EPHEMERAL_LABELS mechanism and the rebuild --only sidecars purge path that TASK-5.3 built - both already handle a set of arbitrary size.
<!-- SECTION:DESCRIPTION:END -->
