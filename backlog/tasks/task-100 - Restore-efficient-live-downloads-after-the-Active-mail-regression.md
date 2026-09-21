---
id: TASK-100
title: Restore efficient live downloads after the Active-mail regression
status: In Progress
assignee: []
created_date: '2026-09-21 05:03'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 100500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
TASK-28 routed normal downloads through full live synchronization, bypassing incremental candidate selection and batched content reads. IMAP now issues per-message metadata requests and repeats folder discovery, selection, identity search, and content fetch for every refreshed message. Gmail content refresh remains serial after the TASK-97 metadata batching fix. Restore efficient first and repeat downloads while preserving fresh lifecycle observations, immutable owned files, source/account scope, complete labels, and conservative recovery from partial results.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Synthetic first-run and unchanged-repeat workloads for Gmail and IMAP demonstrate bounded batch request counts instead of per-message network round trips.
- [ ] #2 Unchanged safe-to-reuse content avoids repeated remote body downloads while fresh lifecycle state is still checked; new, changed, unknown, and incomplete observations remain safe and retryable.
- [ ] #3 The normal CLI and web download path uses the optimized implementation, preserving filters, source/account isolation, owned-file verification, progress, and interruption behavior.
- [ ] #4 Regression and mutation checks cover lifecycle transitions, partial batch responses, changed identities, cache corruption, and resume; independent review and the full pre-push gate pass.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 033390c. Implement and test in an isolated checkout to avoid reloading the active server. Batch IMAP metadata/content reads and Gmail content reads, avoid per-message repeated catalog/folder lookups, and reuse verified content only under documented stable identity/revision guarantees. Reduce repeated local ownership lookup work without schema changes. Prove improvements using initial, unchanged-repeat, and changed-message synthetic request counts before integrating onto master.
<!-- SECTION:PLAN:END -->
