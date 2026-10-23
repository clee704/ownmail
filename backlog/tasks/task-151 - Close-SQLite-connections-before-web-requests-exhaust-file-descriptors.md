---
id: TASK-151
title: Close SQLite connections before web requests exhaust file descriptors
status: To Do
assignee: []
created_date: '2026-10-23 06:46'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 120000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Search requests can return HTTP 500 when SQLite connections accumulate until garbage collection. Confirmed against a real archive: SQLite unable-to-open errors coincided with operating-system Too many open files errors. ArchiveDatabase._connect, consolidated_count, and other direct connection contexts use the SQLite transaction context manager without deterministic connection closure. The service subsequently returned HTTP 200 without a restart; the underlying resource-lifetime defect remains.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Request-scoped SQLite connections close on success and exception without relying on garbage collection.
- [ ] #2 Existing commits, rollbacks, and pinned read-only search snapshots retain their behavior.
- [ ] #3 A synthetic regression with garbage collection disabled or a low descriptor limit detects the current failure and passes with deterministic closure.
- [ ] #4 The full pre-push gate passes and the fix is committed.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Diagnosis only; no production files, database schema, archive contents, or service configuration changed. Synthetic probe under the same Python runtime used a temporary database, disabled garbage collection, and set the child process descriptor limit to 128: the existing transaction-context pattern failed after 125 opens with unable to open database file. After explicit collection, closing(sqlite3.connect(...)) combined with the transaction context completed 250 opens under the same limit with collection still disabled. Temporary files were removed. Audit connection ownership before changing helpers: the existing-data JSON search subclass intentionally reuses a pinned connection through nullcontext and must retain its snapshot. Current short-lived descriptors also dropped between requests without restarting, consistent with deferred garbage collection.
<!-- SECTION:NOTES:END -->
