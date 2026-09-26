---
id: TASK-84
title: Count indexing failures in download outcomes
status: To Do
assignee: []
created_date: '2026-09-14 07:25'
updated_date: '2026-09-26 02:23'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
EmailArchive.backup ignores a false return from _index_email, increments success_count, and may advance the sync cursor even though indexing failed. Download progress can report the failure, but the underlying download result and cursor policy still treat the operation as successful.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A failed index operation is represented in the download result and prevents the run from being reported as fully successful.
- [ ] #2 Sync-state and retry behavior after an indexing failure preserve the ability to recover the affected message, with a synthetic regression.
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: affects the default EmailArchive.backup path only; the live path rolls back the row on indexing failure. backup also sets indexed_hash when indexing failed, which can hide the message from later reindex checks, and the sync cursor still advances when error_count is 0.
<!-- SECTION:NOTES:END -->
