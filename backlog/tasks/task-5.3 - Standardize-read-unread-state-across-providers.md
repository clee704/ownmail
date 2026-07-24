---
id: TASK-5.3
title: Standardize read/unread state across providers
status: To Do
assignee: []
created_date: '2026-07-24 04:56'
updated_date: '2026-07-24 05:10'
labels: []
milestone: m-1
dependencies: []
parent_task_id: TASK-5
priority: high
ordinal: 4
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Read/unread state is represented completely differently per provider: standard IMAP (RFC 3501) uses the \Seen flag on the message (boolean, not a label); Gmail's REST API (which ownmail's gmail.py uses, not IMAP) exposes it as a pseudo-label 'UNREAD' mixed in with real labels. imap.py currently has NO handling of the \Seen flag at all - the 'seen'/'_seen_map' names in that file are unrelated local dedup bookkeeping (which folders a message-ID appeared in), not the IMAP flag. Net effect: Gmail-sourced archives get an UNREAD pseudo-label, IMAP-sourced archives get no read/unread information at all today. Needs: (1) imap.py fetch FLAGS (or add \Seen to the existing FETCH call) and represent read/unread consistently with however Gmail's UNREAD is modeled - probably as a normalized boolean/column rather than continuing to overload the labels string for something that isn't a topical label, (2) decide whether to keep exposing it via label: search syntax for backward compat, a dedicated is:unread-style filter, or both.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 IMAP sync captures \Seen and stores read/unread state
- [ ] #2 Read/unread represented consistently across Gmail and IMAP sources (same underlying field, not label-string-only for one and absent for the other)
<!-- AC:END -->
