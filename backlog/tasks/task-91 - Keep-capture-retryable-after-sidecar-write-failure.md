---
id: TASK-91
title: Keep capture retryable after sidecar write failure
status: To Do
assignee: []
created_date: '2026-09-15 02:38'
labels: []
dependencies: []
references:
  - ownmail/archive.py
priority: high
type: bug
ordinal: 94000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
At abda815, EmailArchive.backup marks a message downloaded before writing its required label sidecar. If sidecar.write_labels raises OSError, the outer finally block commits the incomplete row. A synthetic provider reproduction confirms that the next backup filters out that ID, performs no download, reports no new mail, and leaves the sidecar missing. Keep an incomplete contents-and-labels save retryable, preserve completed owned copies, and continue unrelated captures after recoverable per-message storage failures. This is separate from TASK-90, which handles label retrieval failure before saving. TASK-28 must account for the same failure during Active promotion.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A failed sidecar write does not finalize a downloaded record; a later successful backup retries and saves the required labels.
- [ ] #2 Recoverable per-message storage failures are reported and do not prevent unrelated messages from completing.
- [ ] #3 Interrupted capture preserves completed message progress and does not advance the sync cursor past incomplete saves.
- [ ] #4 Regression tests reproduce the failure against the previous behavior and verify successful retry without replacing completed owned contents or labels.
<!-- AC:END -->
