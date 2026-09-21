---
id: TASK-100
title: Restore efficient live downloads after the Active-mail regression
status: In Progress
assignee: []
created_date: '2026-09-21 05:03'
updated_date: '2026-09-21 05:22'
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
- [x] #1 Synthetic first-run and unchanged-repeat workloads for Gmail and IMAP demonstrate bounded batch request counts instead of per-message network round trips.
- [x] #2 Unchanged safe-to-reuse content avoids repeated remote body downloads while fresh lifecycle state is still checked; new, changed, unknown, and incomplete observations remain safe and retryable.
- [x] #3 The normal CLI and web download path uses the optimized implementation, preserving filters, source/account isolation, owned-file verification, progress, and interruption behavior.
- [x] #4 Regression and mutation checks cover lifecycle transitions, partial batch responses, changed identities, cache corruption, and resume; independent review and the full pre-push gate pass.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Review base: 033390c. Implement and test in an isolated checkout to avoid reloading the active server. Batch IMAP metadata/content reads and Gmail content reads, avoid per-message repeated catalog/folder lookups, and reuse verified content only under documented stable identity/revision guarantees. Reduce repeated local ownership lookup work without schema changes. Prove improvements using initial, unchanged-repeat, and changed-message synthetic request counts before integrating onto master.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Implemented bounded Gmail content reads, IMAP metadata/content reads, fresh lifecycle scans with revision-based reuse of verified Active payloads, and an account-scoped in-memory ownership lookup. Gmail end-to-end synthetic workload with 101 messages uses 11 HTTP requests initially, 5 on an unchanged repeat with no body downloads, and 7 after one content revision changes. IMAP scan workload with 1,000 messages uses five commands. Independent review and full validation are in progress. Reuse relies on Gmail message historyId (https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages) and the IMAP mailbox/UIDVALIDITY/UID immutable-content guarantee (https://www.rfc-editor.org/rfc/rfc9051.html#section-2.3.1.1). Metadata is freshly scanned each run; this change does not restore the old arrival-only history cursor.

Independent GPT-6 Astra and Claude Opus 5 reviews found no remaining production issues after final fixes. Updated CLI/subprocess provider fixtures for the batch interface without weakening assertions; batch boundaries now flush completed progress before the next network read. The touched IMAP parser also rejects quoted flags that could otherwise be masked into eligible state. Targeted lifecycle, ownership, Gmail, IMAP, progress and interruption tests pass. Deliberate mutations verify batching, content reuse, fresh eligible-state checks, ownership file checks and payload-write avoidance. Full gate is being rerun on the stable final tree.

Final pre-push gate passed with browser tests required: all file checks, Ruff, deptry and the full coverage-gated suite. Targeted CLI/progress validation passes all 147 tests without assertion changes. Code is ready to apply to the running checkout; no schema, dependency, credential or owned-file deletion behavior changed.
<!-- SECTION:NOTES:END -->
