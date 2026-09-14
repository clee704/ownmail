---
id: TASK-83
title: Show download progress and failure reasons in Settings
status: In Progress
assignee: []
created_date: '2026-09-14 07:23'
updated_date: '2026-09-14 07:38'
labels: []
dependencies: []
type: enhancement
ordinal: 87000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Make download status useful while a run is active and after a failure. Show actual downloaded, skipped, and failed message counts, the current source, and a short error explanation. Replace the disconnected scheduling hints with concise, coherent guidance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Settings displays live cumulative counts that distinguish newly archived mail from duplicate or deleted messages and download errors.
- [x] #2 Failed runs show a brief useful reason without exposing credentials, message content, or raw exception output; final progress remains visible until the next run.
- [x] #3 Scheduling guidance reads as one concise paragraph, and browser checks cover live updates, failure text, reset, and mobile layout.
- [x] #4 Progress reporting preserves existing download, retry, locking, shutdown, and resume behavior; focused regressions and full pre-push checks pass.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Send structured progress from the download subprocess through a private temporary JSON snapshot. Reuse archive events for accurate counters, classify failures into safe explanations, and consume progress in the existing status API. Update the Settings copy and live status, then verify through synthetic downloads, browser tests, and independent review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The existing task for Settings focus borders is unrelated and remains with its current owner. This task does not change credential access, OAuth behavior, archive deletion, or database schema.

The Settings copy is now one paragraph. Browser regressions verify changing counts, source and phase, safe failure text, reset on a new run, zero results versus unavailable progress, and phone layout. Manager tests verify final snapshot retention, retry reset, validation, and private temporary-file cleanup. The pre-existing download outcome and cursor behavior after indexing failures is tracked separately in TASK-84.

A real CLI subprocess regression verifies live cumulative counts through the web API across two synthetic sources, duplicate and deleted-message skips, a partial failure, final snapshot retention, and configuration/setup failures with zero attempted-message errors. Suppressing downloaded increments deliberately makes the live-count assertion fail. Failure details remain hidden during later sources and appear once at completion.

All pre-push checks pass with browser tests required, including the full suite and coverage gate. Independent review verified the producer and manager, then drove regressions for duplicate terminal wording and stale reasons beside a later source. Mutation checks reject lost final counts, leaked exception text, miscounted duplicates, and stale or repeated UI reasons. Existing indexing-result and retry behavior remains documented in TASK-84.
<!-- SECTION:NOTES:END -->
