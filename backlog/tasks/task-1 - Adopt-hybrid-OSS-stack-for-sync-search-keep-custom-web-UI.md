---
id: TASK-1
title: 'Adopt hybrid OSS stack for sync/search, keep custom web UI'
status: Done
assignee: []
created_date: '2026-07-23 18:44'
updated_date: '2026-07-23 19:22'
labels:
  - architecture
dependencies: []
documentation:
  - backlog/docs/doc-1 - Hybrid-OSS-Stack-Migration.md
priority: medium
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Umbrella task for migrating sync/search onto mbsync + notmuch where it makes sense, while keeping the Gmail API provider and the whole web UI custom. See doc-1 for full rationale.
<!-- SECTION:DESCRIPTION:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Epic complete. Final outcome after review with the user:

- TASK-1.1 (notmuch benchmark): NO-GO on replacing SQLite FTS5 - FTS5 already wins or ties; notmuch only reaches parity via a bindings integration that adds dependency + concurrency cost for no gain.
- TASK-1.5 (search syntax mapping): closed without implementation - direct consequence of the 1.1 no-go.
- TASK-1.2 (mbsync prototype): built, then REVERTED after review. providers/imap.py already covers everything mbsync would add (folder labels, dedup, incremental sync) without a second on-disk layout or external dependency. No concrete pain point with imap.py motivated adopting it - same speculative shape as the notmuch task. NO-GO on adopting mbsync.
- TASK-1.4 (Gmail/Maildir guard): moot given 1.2's reversal - there is no IMAP-based sync path at all now, so nothing could violate the constraint. GmailProvider remains untouched and is the sole Gmail sync/label path.
- TASK-1.3 (label sidecars): the one part of this epic that shipped. Implemented, wired into download/update-labels/trash/restore/delete, with `rebuild --only sidecars` for backfill/reconciliation. Validated against real archive content. This had nothing to do with the search or sync verdicts and stands on its own merit.

Net result: of doc-1's three proposed changes (search backend, sync backend, label storage), two were evaluated and rejected on their technical merits, one shipped. GmailProvider and the Flask web UI are completely untouched, as intended from the start.
<!-- SECTION:NOTES:END -->
