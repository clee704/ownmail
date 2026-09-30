---
id: TASK-110
title: Retry throttled Gmail live batches without losing successful members
status: Done
assignee:
  - Ownmail IC1
created_date: '2026-09-22 05:48'
updated_date: '2026-09-30 08:10'
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
- [x] #1 Transient member failures are retried within a bounded budget without repeating successful reads.
- [x] #2 Exhausted and permanent failures preserve retryable state and report an incomplete refresh.
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

The task-only plan was committed as dcbffaf1d52beb5eb8a0eef372623c36c64ebd47 before implementation. The bounded helper now retries only explicit 429/503 members, retains successful/permanent results, and stops retrying on missing/duplicate/unexpected callbacks or whole-batch exceptions. Tests assert exact member IDs, 1s/2s backoff, three-attempt exhaustion, unchanged batch50, interruption propagation, and cached bytes/capture cursor preservation followed by later recovery. New regressions failed against the original helper (12 failures, plus eight retry-callback cases) and the implemented focused suite passed 68 tests. The broader provider/live-sync/recovery suite passed 408 tests. Ruff check, Ruff format-check and deptry passed. Author review against the original review base and a fresh independent Astra Ultra review found no actionable issues; 13 additional mocked helper probes passed. No product code outside the assigned helper/import or real service operations changed.

Implementation checkpoint faa4b3c57eb210a4e2bf775509ccc69e268f75c4 passed the complete required pre-commit pre-push gate with mandatory headless Chromium, unchanged test selection and 95% branch-inclusive coverage floor: 3976 passed, one expected failure, 96.54% coverage in 188.70s. All 13 browser launch/close probes exited cleanly. The runtime-only observer preserved original timeouts and assertions; maxfail=1 stopped only on a first failure and the full suite completed successfully. File hygiene, Ruff check/format and deptry hooks passed; explicit Ruff format-check also passed. The implementation and final task commits use normal commit/message hooks. Local validation used Python 3.14.6; the supported-version CI matrix remains a later integration check. No integration or publication was performed.
Next action: no implementation work remains; preserve this clean local branch for separately authorized integration and supported-version CI.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented bounded per-member Gmail live retries for explicit HTTP 429/503 failures with three total attempts and 1s/2s backoff. Successful/permanent observations are never reread, live batch50 is retained, and structural/outer failures and cancellation remain conservative. Synthetic metadata/content regressions cover recovery, exhaustion, exact member reads, cached-content/cursor preservation and later resumption. The complete mandatory-browser pre-push gate passed with 3976 tests, one expected failure and 96.54% coverage. Author review and fresh independent Astra Ultra review found no actionable issues. Local only; integration/publication remain separately coordinated.
<!-- SECTION:FINAL_SUMMARY:END -->
