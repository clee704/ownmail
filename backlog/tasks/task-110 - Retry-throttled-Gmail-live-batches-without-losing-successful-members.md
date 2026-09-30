---
id: TASK-110
title: Retry throttled Gmail live batches without losing successful members
status: In Progress
assignee:
  - Ownmail IC1
created_date: '2026-09-22 05:48'
updated_date: '2026-09-30 07:53'
labels: []
dependencies: []
priority: medium
type: bug
ordinal: 14000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Live refreshes can receive per-message HTTP 429 responses inside a successful Gmail batch. The live path has no bounded member retry, leaving the source incomplete until a later run. Reuse provider request limits and add bounded backoff for transient failures while preserving successful members and conservative handling of permanent errors.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Transient member failures are retried within a bounded budget without repeating successful reads.
- [ ] #2 Exhausted and permanent failures preserve retryable state and report an incomplete refresh.
<!-- AC:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Start isolated branch fix/retry-live-gmail-batch-members from clean TASK-98 closure cbb90b81e5b0b1ad87164bc5998643302a8b0a69. Commit this task-only claim/plan with normal hooks before product or test changes.
2. Limit production changes to live_gmail._message_batch and its necessary time import. Retry only explicit failed HTTP 429/503 members, at most three total attempts with one- and two-second backoff, retaining the established live batch limit of 50. Never repeat successful or permanent members.
3. Preserve the helper return contract and current callers, member 404 distinctions, structural callback failure handling, whole-batch failures, catalog behavior and KeyboardInterrupt propagation. Track callbacks against the IDs requested in each attempt; duplicate observations remain invalid, successful earlier members remain intact, and recovered transient failures no longer mark an otherwise complete snapshot incomplete.
4. Extend only tests/test_live_gmail_batch.py and tests/test_live_gmail_content.py with scripted synthetic transport/clock evidence for metadata/content recovery, exact attempted IDs, bounded exhaustion, permanent failures, malformed/missing callbacks, 404 and interruption. Cover downstream cached-content/cursor retention and later recovery without real mail, credentials, authentication or external requests.
5. Verify failing-before/passing-after regressions, focused retained behavior, Ruff check/format-check, deptry, author review and the complete mandatory-browser pre-push gate using private runtime state. Record verified ACs and clean local commits with normal hooks. No master, merge/rebase, publication, TASK-37 policy or TASK-125 changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Premise verified on cbb90b81e5b0b1ad87164bc5998643302a8b0a69 using the real Google client over the existing synthetic GmailTransport with network, authentication and keyring access forbidden. A transient m1 member 429 leaves metadata incomplete and raw m1 failed after one batch; m0/m2 succeed, no automatic backoff occurs, and a second explicit call recovers m1 while rereading all members. Independent Astra Ultra read-only preflight confirms the shared missing behavior is live_gmail._message_batch. The manager accepted the bounded policy supported by existing capture retry evidence: explicit 429/503 only, three total attempts, delays 1s/2s, and unchanged live-50 contract. Capture whole-batch result clearing and batch10/delay0.2 behavior are not copied or changed. Whole-batch exceptions and missing/duplicate/unexpected callbacks remain conservative rather than becoming new retry causes. No new runtime dependencies, schema, OAuth/token/credential handling or real-message operations are in scope. Exact owned files: ownmail/providers/live_gmail.py (batch helper and required time import), tests/test_live_gmail_batch.py, tests/test_live_gmail_content.py and this task ledger. Review base remains cbb90b81e5b0b1ad87164bc5998643302a8b0a69 across all checkpoints.
Next action: prepare a fresh source-bound private environment and commit this task-only plan with normal hooks before implementation.
<!-- SECTION:NOTES:END -->
