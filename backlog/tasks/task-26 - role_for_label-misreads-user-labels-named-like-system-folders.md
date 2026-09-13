---
id: TASK-26
title: role_for_label misreads user labels named like system folders
status: To Do
assignee: []
created_date: '2026-07-26 05:31'
updated_date: '2026-09-13 18:18'
labels:
  - bug
dependencies: []
priority: medium
ordinal: 31000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
roles.role_for_label() resolves a STORED label string by trying the Gmail label-ID map, then the IMAP leaf-name table under both hierarchy delimiters. The name table is case-insensitive and matches on the leaf, so any user label whose name happens to collide with a system-folder spelling resolves to that role.

Confirmed in a real archive. Synthetic example: a user label 'Archive' (with a child 'Archive/Example') resolves to role archive. The consequences are all in the post-capture read paths:

- _build_label_nav (web.py:1190) skips any label with a truthy role_for_label, so 'Archive' vanishes from the user-label list and is folded into the system Archive entry — while its child 'Archive/Example' stays under user labels, because the leaf 'Example' matches nothing. One label tree, split across two sections, with the parent renamed.
- _label_chips (web.py:1153) renames the chip to the role's display name and links it to role:archive instead of label:"Archive".
- A role: search resolves the union of every label with that role, so role:archive returns the user label's messages.

The table's false-positive surface is wide: 'Trash', 'Bin', 'Drafts', 'Sent', 'Home' near-misses, and every localized spelling in _FOLDER_NAMES. Gmail user labels are freely named, so collisions are expected rather than exotic.

WHY THIS IS NOT JUST doc-7'S ACCEPTED COST: doc-7 accepted that a folder identifiable only by SPECIAL-USE cannot be re-resolved offline — a FALSE NEGATIVE, and it argued the case was narrow because such folders are excluded at sync time so the message never lands. This is the opposite direction: a false POSITIVE on a label that is legitimately in the archive, in a read path doc-7 was not reasoning about.

Approach to weigh: at capture the provider signal is unambiguous (exact Gmail label IDs; SPECIAL-USE flags plus the reported delimiter), and only the post-capture read paths are guessing. Options include restricting role_for_label's name-table branch to labels that came from a folder-shaped source, recording the resolved role at capture (doc-7 notes a sync_state cache needs no schema change), or narrowing the read paths to exact Gmail system label IDs the way EPHEMERAL_LABELS already does.

Blocks nothing, but TASK-25 must not build its stale-label hiding on the unrestricted heuristic — hiding a user label named 'Trash' would make real archive content invisible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A user label whose name collides with a system-folder spelling stays in the user-label section under its own name
- [ ] #2 Its chip links to label:"<raw>", not to role:<slug>
- [ ] #3 A role: search does not return messages whose only matching label is a user label
- [ ] #4 Genuine provider system labels still resolve to their role
<!-- AC:END -->
