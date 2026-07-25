---
id: TASK-19
title: >-
  Configurable label exclusion for platform auto-labels (IMPORTANT, CATEGORY_*,
  STARRED)
status: To Do
assignee: []
created_date: '2026-07-25 06:20'
updated_date: '2026-07-25 06:28'
labels: []
dependencies: []
priority: medium
ordinal: 24000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-5.3 dropped Gmail's UNREAD unconditionally: nothing refreshes a captured value, so an archived 'unread' becomes false over time. Gmail's other non-topical pseudo-labels still pass through _resolve_label_names into the labels array, but they are a different kind of question.

## Correctness vs taste

The line: does the stored value become **false**, or merely **unwanted**?

- UNREAD becomes false -> stays hardcoded in roles.EPHEMERAL_LABELS. Deliberately NOT configurable; a knob there would only let a user opt into a lie.
- IMPORTANT stays true as a statement about the past ('Gmail flagged this at delivery') even if the user considers it worthless noise. Taste.
- CATEGORY_PERSONAL/SOCIAL/PROMOTIONS/UPDATES/FORUMS - Gmail's tab classification, stable and topical. Taste, and the weakest case for dropping.
- CHAT - marks Hangouts/Chat messages, closer to a message type than a label.

So this task is no longer 'decide per label'. It is: ship a per-source exclude_labels config knob and let the user decide, keeping the maintainer out of a taste call.

## Design

Mirror exclude_folders (see doc-7) with one deliberate difference: **default to keep**, not to a role-based default set.

exclude_folders can afford an opinionated default because its effect is loud - a missing folder is obvious. Dropping a label from a message that WAS downloaded is silent, and irreversible without a full re-sync. So the knob is opt-in: archive whatever the provider sent unless the config names something.

This makes the setting forward-reversible only - a user can always drop labels later, and rebuild --only sidecars applies the config retroactively via the purge path TASK-5.3 built, but nothing recovers a label already dropped. State that in the docs.

## Open question this does NOT resolve

STARRED is a deliberate user act and the strongest candidate for archiving, but ownmail never reads IMAP's \\Flagged. Keeping STARRED therefore reintroduces exactly the Gmail/IMAP asymmetry TASK-5.3 closed for UNREAD. Config does not fix that. Decide separately: capture \\Flagged too, or accept the gap knowingly and document it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-source exclude_labels config option, defaulting to keep everything the provider sent
- [ ] #2 Excluded labels are dropped at capture for both Gmail and IMAP sources
- [ ] #3 rebuild --only sidecars applies the current exclude_labels to existing archives
- [ ] #4 UNREAD stays unconditional in roles.EPHEMERAL_LABELS and is not reachable via config
- [ ] #5 Docs state that dropping is not reversible without a re-sync
- [ ] #6 STARRED vs IMAP \\Flagged asymmetry is decided and recorded, not left implicit
<!-- AC:END -->
