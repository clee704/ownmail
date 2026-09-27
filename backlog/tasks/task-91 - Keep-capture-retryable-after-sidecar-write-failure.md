---
id: TASK-91
title: Keep capture retryable after sidecar write failure
status: Done
assignee: []
created_date: '2026-09-15 02:38'
updated_date: '2026-09-27 06:20'
labels: []
dependencies: []
references:
  - ownmail/archive.py
priority: high
type: bug
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
EmailArchive.backup, the default download path when a source does not enable active_downloads, marks a message downloaded before writing its required label sidecar. If sidecar.write_labels raises OSError, the outer finally block commits the incomplete row. A synthetic provider reproduction confirms that the next backup filters out that ID, performs no download, reports no new mail, and leaves the sidecar missing. Keep an incomplete contents-and-labels save retryable, preserve completed owned copies, and continue unrelated captures after recoverable per-message storage failures. This is separate from TASK-90, which handles label retrieval failure before saving. The live capture path added by TASK-28 writes the sidecar before registering the row and records failures as retryable, so it does not have this bug.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A failed sidecar write does not finalize a downloaded record; a later successful backup retries and saves the required labels.
- [x] #2 Recoverable per-message storage failures are reported and do not prevent unrelated messages from completing.
- [x] #3 Interrupted capture preserves completed message progress and does not advance the sync cursor past incomplete saves.
- [x] #4 Regression tests reproduce the failure against the previous behavior and verify successful retry without replacing completed owned contents or labels.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Write the label sidecar before mark_downloaded in EmailArchive.backup, so a row exists only once its sidecar does. Catch per-message OSError from the stat and sidecar write, report it as a storage failure (error_count, failed_ids, progress.fail_exception) and continue with the next message. The saved .eml stays in place; the retry rewrites it at the same deterministic path. error_count > 0 already keeps the sync cursor in place, and a hard interrupt during the write leaves no row for the finally-commit to persist. Tests in tests/test_archive.py: sidecar OSError then successful retry, unrelated messages complete, hard interrupt mid-write keeps earlier rows and cursor. Review base: a7c16a5.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
backup now writes the label sidecar before mark_downloaded, so a committed row always has its sidecar. An OSError from the stat or sidecar write is reported as a per-message archive failure (error_count, failed_ids, progress.fail_exception) and the loop continues. The failed message's content hash is not added to the in-run dedup set, and no row exists, so the next backup downloads it again and rewrites the .eml at the same deterministic path. error_count > 0 keeps the sync cursor in place. A forced quit (SystemExit) during the sidecar write leaves no row for the finally-commit to persist, while earlier rows are kept.

Caveat: after a sidecar failure the saved .eml stays on disk without a sidecar or row until the retry. Removing it would delete an email file, which is a STOP item; the live capture path leaves files the same way. A scan-archive run before the retry would register it as an unlabelled local import.

Verification: two regressions in tests/test_archive.py::TestBackupSidecarFailure fail against the previous archive.py and pass with the fix; pre-push gate passes.
<!-- SECTION:NOTES:END -->
