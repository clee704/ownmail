---
id: TASK-84
title: Count indexing failures in download outcomes
status: Done
assignee: []
created_date: '2026-09-14 07:25'
updated_date: '2026-09-27 14:32'
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
- [x] #1 A failed index operation is represented in the download result and prevents the run from being reported as fully successful.
- [x] #2 Sync-state and retry behavior after an indexing failure preserve the ability to recover the affected message, with a synthetic regression.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Keep the downloaded row when indexing fails: the .eml, sidecar and row are a complete capture, and the owned copy must stay recorded even if the server copy disappears before a retry. Leave indexed_hash NULL so 'ownmail rebuild' selects the message, count it in error_count and failed_ids instead of success_count, and print the rebuild instruction. error_count > 0 keeps the sync cursor in place. This differs from TASK-91, where the capture itself was incomplete. Regression in tests/test_archive.py: a synthetic index failure reports an error, holds the cursor, leaves the row selectable by rebuild, and rebuild makes it searchable. Review base: 1e71b4a.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-09-25 review: affects the default EmailArchive.backup path only; the live path rolls back the row on indexing failure. backup also sets indexed_hash when indexing failed, which can hide the message from later reindex checks, and the sync cursor still advances when error_count is 0.

Indexing failure in EmailArchive.backup is now a per-message error: error_count and failed_ids include it, success_count and the downloaded progress count do not, so cmd_download returns False (exit 1) and the sync cursor stays in place. The row is kept and indexed_hash stays NULL, so 'ownmail rebuild' selects the message; the console prints that instruction.

Decision: keep the row rather than roll it back as the live path does. The .eml, sidecar and row form a complete capture, and a rolled-back row would leave the owned copy unrecorded if the server copy disappeared before the retry. The index is derived, so rebuild is the repair path. TASK-91 differs because its capture was incomplete.

Caveat: a later download does not retry indexing. It filters the message as already downloaded, reports success when nothing else fails, and advances the cursor. The message stays out of search until rebuild runs.

Verification: tests/test_archive.py::TestBackupIndexFailure fails against 1e71b4a (success_count 3) and passes with the fix; setting indexed_hash on failure makes it fail after rebuild. Pre-push gate passes.
<!-- SECTION:NOTES:END -->
