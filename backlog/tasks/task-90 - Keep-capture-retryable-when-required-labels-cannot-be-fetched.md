---
id: TASK-90
title: Keep capture retryable when required labels cannot be fetched
status: To Do
assignee: []
created_date: '2026-09-14 09:05'
labels: []
milestone: m-5
dependencies: []
references:
  - ownmail/providers/gmail.py
  - ownmail/archive.py
documentation:
  - docs/philosophy.md
priority: high
type: bug
ordinal: 6
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Required label lookup failures must not finalize an archive capture with an empty label snapshot. Gmail download_message and the batch fallback currently coerce the None failure result from _get_labels_for_message to [], while archive.backup writes the sidecar and marks the message captured. A synthetic provider with successful raw retrieval and a None label result reproduces a successful download with empty labels. TASK-20 fixed the backfill command but explicitly retained this download behavior; the ownership design now requires a successful contents-and-labels handoff. Fix this existing capture path independently of the Active view. Preserve configured label omission and genuinely empty label responses; do not resnapshot already owned messages.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Single-message and batch-fallback label lookup failures are reported as retryable capture failures when label capture is enabled, without finalizing an owned copy or silently recording empty labels.
- [ ] #2 A confirmed empty label set and explicit include_labels: false remain distinguishable from a failed required lookup and behave as documented.
- [ ] #3 Regression coverage demonstrates a failed lookup followed by successful retry preserves the labels once, keeps unrelated captures progressing, and keeps failed messages eligible for later retry.
- [ ] #4 Already archived files and labels remain unchanged; no automatic historical label resnapshot is introduced.
<!-- AC:END -->
