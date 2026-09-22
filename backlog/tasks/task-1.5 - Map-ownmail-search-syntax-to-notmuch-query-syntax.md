---
id: TASK-1.5
title: Map ownmail search syntax to notmuch query syntax
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-09-22 17:25'
labels:
  - search
dependencies: []
parent_task_id: TASK-1
priority: medium
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Translate existing search operators (from:, subject:, label:, attachment:) to notmuch query syntax where possible.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Superseded by the TASK-1.1 NO-GO in the notes: from:/subject:/date:/label: map to notmuch equivalents
- [ ] #2 Superseded by the TASK-1.1 NO-GO in the notes: attachment: has no notmuch equivalent - implement via tag-on-ingest instead
- [ ] #3 Superseded by the TASK-1.1 NO-GO in the notes: Existing search test cases pass against notmuch backend
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Closed without implementation per user decision after TASK-1.1 benchmark came back NO-GO: notmuch does not beat current SQLite FTS5 for the built-in web UI search, and the bindings-based integration path that would reach parity adds a system dependency + reader/writer concurrency problem for no net gain. Query syntax mapping work is not worth doing against that backend. Revisit only if a new driver for notmuch adoption emerges (e.g. external MUA interop), which is out of scope today. TASK-1.2 (mbsync)/1.3 (sidecars)/1.4 (Gmail label constraint) proceed independently - they do not depend on the search backend choice.

**Ledger repair, 2026-09-22 (TASK-42).** All three criteria describe the notmuch backend that TASK-1.1 rejected, so they are marked superseded rather than met.
<!-- SECTION:NOTES:END -->
